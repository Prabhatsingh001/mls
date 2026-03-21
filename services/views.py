from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.db import transaction

from auditapp.models import AuditLog
from auditapp.utils import _log_details
from auditapp.tasks import record_audit_log_tasks
from authentication.decorators import role_required
from authentication.models import TechnicianProfile, User

from .models import Project, ProjectExtraMaterial, ServiceItem, ServiceItemMapping


@login_required()
@role_required([User.Role.TECHNICIAN])
def tech_dashboard(request):
    tech_profile, _ = TechnicianProfile.objects.get_or_create(user=request.user)

    assigned_projects = Project.objects.filter(technician=request.user).select_related(
        "job_request__service", "job_request__customer"
    )

    stats = {
        "active": assigned_projects.filter(
            status__in=[
                Project.Status.PENDING,
                Project.Status.SCHEDULED,
                Project.Status.ONGOING,
            ]
        ).count(),
        "completed": assigned_projects.filter(status=Project.Status.COMPLETED).count(),
        "total": assigned_projects.count(),
    }

    tab = request.GET.get("tab", "active")

    if tab == "completed":
        projects = assigned_projects.filter(status=Project.Status.COMPLETED).order_by(
            "-completion_date"
        )
    else:
        projects = assigned_projects.filter(
            status__in=[
                Project.Status.PENDING,
                Project.Status.SCHEDULED,
                Project.Status.ONGOING,
            ]
        ).order_by("-job_request__created_at")

    return render(
        request,
        "services/tech.html",
        {
            "tech_profile": tech_profile,
            "projects": projects,
            "stats": stats,
            "tab": tab,
        },
    )


@login_required()
@role_required([User.Role.TECHNICIAN])
@require_POST
def technician_toggle_availability(request):
    """Allow technicians to toggle their availability status."""
    tech_profile, _ = TechnicianProfile.objects.get_or_create(user=request.user)
    tech_profile.is_available = not tech_profile.is_available
    tech_profile.save()
    status = "available" if tech_profile.is_available else "unavailable"
    messages.success(request, f"You are now {status} for new job assignments.")
    return redirect("services:tech-dashboard")


@login_required()
@role_required([User.Role.TECHNICIAN])
def view_assignend_project_details(request, project_id):
    """View details of a specific project assigned to the technician."""
    project = get_object_or_404(
        Project.objects.select_related(
            "job_request__service__category", "job_request__customer"
        ).prefetch_related("job_request__service__included_items__item"),
        pk=project_id,
        technician=request.user,
    )

    required_materials = ServiceItemMapping.objects.select_related("item").filter(
        service=project.job_request.service,
        item__item_type=ServiceItem.ItemType.MATERIAL,
    )
    extra_materials = ProjectExtraMaterial.objects.select_related(
        "catalog_item", "added_by"
    ).filter(project=project)
    material_catalog = ServiceItem.objects.filter(
        item_type=ServiceItem.ItemType.MATERIAL,
        is_available=True,
    ).order_by("name")

    context = {
        "project": project,
        "required_materials": required_materials,
        "extra_materials": extra_materials,
        "material_catalog": material_catalog,
    }
    return render(request, "services/project_details.html", context)


def join_as_technician(request):
    """Static landing page encouraging technicians to sign up."""
    return render(request, "join_as_technician.html")


@login_required()
@role_required([User.Role.TECHNICIAN])
@require_POST
def add_project_extra_material(request, project_id):
    """Let technician record additional materials needed on-site."""
    project = get_object_or_404(Project, pk=project_id, technician=request.user)

    if project.status in (Project.Status.COMPLETED, Project.Status.CANCELLED):
        messages.error(
            request, "Cannot add materials to a completed/cancelled project."
        )
        return redirect("services:project-details", project_id=project.pk)

    catalog_item_id = request.POST.get("catalog_item")
    material_name = request.POST.get("material_name", "").strip()
    quantity_raw = request.POST.get("quantity", "1").strip()
    unit_cost_raw = request.POST.get("unit_cost", "").strip()
    notes = request.POST.get("notes", "").strip()

    catalog_item = None
    if catalog_item_id:
        catalog_item = ServiceItem.objects.filter(
            pk=catalog_item_id,
            item_type=ServiceItem.ItemType.MATERIAL,
            is_available=True,
        ).first()
        if not catalog_item:
            messages.error(request, "Selected material is invalid.")
            return redirect("services:project-details", project_id=project.pk)

    if not catalog_item and not material_name:
        messages.error(
            request,
            "Provide a material name or choose one from the material catalog.",
        )
        return redirect("services:project-details", project_id=project.pk)

    try:
        quantity = int(quantity_raw)
        if quantity <= 0:
            raise ValueError
    except (TypeError, ValueError):
        messages.error(request, "Quantity must be a positive number.")
        return redirect("services:project-details", project_id=project.pk)

    unit_cost = None
    if unit_cost_raw:
        try:
            unit_cost = Decimal(unit_cost_raw)
            if unit_cost < 0:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            messages.error(request, "Unit cost must be a valid non-negative amount.")
            return redirect("services:project-details", project_id=project.pk)

    if catalog_item and not material_name:
        material_name = catalog_item.name

    extra_material = ProjectExtraMaterial.objects.create(
        project=project,
        catalog_item=catalog_item,
        material_name=material_name,
        quantity=quantity,
        unit_cost=unit_cost,
        notes=notes,
        added_by=request.user,
    )

    messages.success(
        request,
        f"Extra material '{extra_material.material_name}' added for this project.",
    )
    return redirect("services:project-details", project_id=project.pk)


@login_required()
@role_required([User.Role.TECHNICIAN])
@require_POST
def update_project_extra_material(request, project_id, extra_material_id):
    """Update an already-recorded extra material for this project."""
    project = get_object_or_404(Project, pk=project_id, technician=request.user)
    extra_material = get_object_or_404(
        ProjectExtraMaterial, pk=extra_material_id, project=project
    )

    if project.status in (Project.Status.COMPLETED, Project.Status.CANCELLED):
        messages.error(
            request,
            "Cannot update materials on a completed/cancelled project.",
        )
        return redirect("services:project-details", project_id=project.pk)

    material_name = request.POST.get("material_name", "").strip()
    quantity_raw = request.POST.get("quantity", "").strip()
    unit_cost_raw = request.POST.get("unit_cost", "").strip()
    notes = request.POST.get("notes", "").strip()

    if not material_name:
        messages.error(request, "Material name is required.")
        return redirect("services:project-details", project_id=project.pk)

    try:
        quantity = int(quantity_raw)
        if quantity <= 0:
            raise ValueError
    except (TypeError, ValueError):
        messages.error(request, "Quantity must be a positive number.")
        return redirect("services:project-details", project_id=project.pk)

    unit_cost = None
    if unit_cost_raw:
        try:
            unit_cost = Decimal(unit_cost_raw)
            if unit_cost < 0:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            messages.error(request, "Unit cost must be a valid non-negative amount.")
            return redirect("services:project-details", project_id=project.pk)

    extra_material.material_name = material_name
    extra_material.quantity = quantity
    extra_material.unit_cost = unit_cost
    extra_material.notes = notes
    extra_material.save()

    messages.success(request, "Extra material updated.")
    return redirect("services:project-details", project_id=project.pk)


@login_required()
@role_required([User.Role.TECHNICIAN])
@require_POST
def delete_project_extra_material(request, project_id, extra_material_id):
    """Remove an extra material entry from this project."""
    project = get_object_or_404(Project, pk=project_id, technician=request.user)
    extra_material = get_object_or_404(
        ProjectExtraMaterial, pk=extra_material_id, project=project
    )

    if project.status in (Project.Status.COMPLETED, Project.Status.CANCELLED):
        messages.error(
            request,
            "Cannot remove materials from a completed/cancelled project.",
        )
        return redirect("services:project-details", project_id=project.pk)

    removed_name = extra_material.material_name
    extra_material.delete()
    messages.success(request, f"Removed extra material '{removed_name}'.")
    return redirect("services:project-details", project_id=project.pk)


@login_required()
@require_POST
def update_project_status(request, project_id):
    """Allow the assigned technician to mark a project as ongoing or completed."""
    try:
        project = Project.objects.get(pk=project_id, technician=request.user)
    except Project.DoesNotExist:
        return render(request, "404.html", status=404)

    new_status = request.POST.get("status")
    if new_status not in (Project.Status.ONGOING, Project.Status.COMPLETED):
        messages.error(request, "Invalid status.")
        return redirect("services:project-details", project_id=project.pk)

    if project.status in (Project.Status.COMPLETED, Project.Status.CANCELLED):
        messages.error(request, "This project can no longer be updated.")
        return redirect("services:project-details", project_id=project.pk)

    project.status = new_status
    if new_status == Project.Status.ONGOING and not project.start_date:
        project.start_date = timezone.now().date()
    elif new_status == Project.Status.COMPLETED:
        project.completion_date = timezone.now().date()
        project.job_request.is_project_completed = True
        project.job_request.save(update_fields=["is_project_completed"])
    project.save()

    log_details = _log_details(
        request,
        category=AuditLog.Category.PROJECT,
        action="status_updated",
        description=f"Technician {request.user.email} updated project PRJ-{project.pk} status to {new_status}",
        target=project,
        metadata={"new_status": new_status},
    )
    transaction.on_commit(lambda: record_audit_log_tasks.delay(log_details))  # type: ignore
    label = dict(Project.Status.choices).get(new_status, new_status)
    messages.success(request, f"Project marked as {label}.")
    return redirect("services:project-details", project_id=project.pk)
