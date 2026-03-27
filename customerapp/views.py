from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.db import transaction

from auditapp.models import AuditLog
from auditapp.utils import _log_details
from auditapp.tasks import record_audit_log_tasks
from authentication.decorators import role_required
from authentication.models import User
from services.models import Category, JobRequest, Project, Service, ServiceItemMapping
from .models import Feedback


@login_required()
@role_required([User.Role.CUSTOMER])
def customer_dashboard(request):
    """Main customer dashboard with tabs: services, my-requests, my-projects."""
    tab = request.GET.get("tab", "services")
    page_number = request.GET.get("page", 1)

    # Stats
    my_requests = JobRequest.objects.filter(customer=request.user).select_related(
        "service", "service__category"
    )
    my_projects = Project.objects.filter(
        job_request__customer=request.user
    ).select_related("job_request__service", "technician")

    feedbacks = Feedback.objects.filter(customer=request.user).count()

    stats = {
        "total_requests": my_requests.count(),
        "pending_requests": my_requests.filter(
            is_reviewed=False, is_converted_to_project=False
        ).count(),
        "active_projects": my_projects.filter(
            status__in=[
                Project.Status.PENDING,
                Project.Status.SCHEDULED,
                Project.Status.ONGOING,
            ]
        ).count(),
        "completed_projects": my_projects.filter(
            status=Project.Status.COMPLETED
        ).count(),
        "cancelled_projects": my_projects.filter(
            status=Project.Status.CANCELLED
        ).count(),
        "feedback_count": feedbacks,
    }

    context = {"tab": tab, "stats": stats}

    if tab == "services":
        services_prefetch = Prefetch(
            "services",
            queryset=Service.objects.filter(is_active=True).prefetch_related(
                Prefetch(
                    "included_items",
                    queryset=ServiceItemMapping.objects.select_related("item").filter(
                        item__is_available=True
                    ),
                )
            ),
        )
        categories = Category.objects.prefetch_related(services_prefetch).all()
        context["categories"] = categories

    elif tab == "my-requests":
        context["requests"] = my_requests.exclude(
            is_converted_to_project=True
        ).order_by("-created_at")

    elif tab == "my-projects":
        context["projects"] = my_projects.order_by("-job_request__created_at")
    
    elif tab == "invoices":
        return redirect(reverse("billing:customer-invoices") + "?page=" + str(page_number))

    return render(request, "customerapp/customer.html", context)


@login_required()
@role_required([User.Role.CUSTOMER])
def customer_create_request(request):
    """Create a new job request."""
    if request.method != "POST":
        return redirect("customerapp:customer-dashboard")

    service_id = request.POST.get("service")
    description = request.POST.get("description", "").strip()
    site_address = request.POST.get("site_address", "").strip()
    preferred_date = request.POST.get("preferred_date", "").strip()

    if not all([service_id, description, site_address, preferred_date]):
        messages.error(request, "All fields are required.")
        return redirect("customerapp:customer-dashboard")

    service = get_object_or_404(Service, pk=service_id, is_active=True)

    job_request = JobRequest.objects.create(
        customer=request.user,
        service=service,
        description=description,
        site_address=site_address,
        preferred_date=preferred_date,
    )

    log_details = _log_details(
        request,
        category=AuditLog.Category.BUSINESS,
        action="booking_created",
        description=f"New job request #{job_request.pk} for '{service.title}' by {request.user.email}",
        target=job_request,
        metadata={"service_id": service.pk, "service_title": service.title},
    )
    transaction.on_commit(lambda: record_audit_log_tasks.delay(log_details))  # type: ignore
    messages.success(
        request, f"Job request for '{service.title}' submitted successfully!"
    )
    return redirect("customerapp:customer-dashboard")


@login_required()
@role_required([User.Role.CUSTOMER])
def customer_edit_job_request(request, job_request_id):
    """Edit a job request that hasn't been converted to a project yet."""
    job_request = get_object_or_404(
        JobRequest,
        pk=job_request_id,
        customer=request.user,
        is_converted_to_project=False,
    )

    if request.method == "POST":
        description = request.POST.get("description", "").strip()
        site_address = request.POST.get("site_address", "").strip()
        preferred_date = request.POST.get("preferred_date", "").strip()

        if not all([description, site_address, preferred_date]):
            messages.error(request, "All fields are required.")
            return redirect("customerapp:customer-dashboard")

        job_request.description = description
        job_request.site_address = site_address
        job_request.preferred_date = preferred_date
        job_request.save()

        messages.success(request, "Job request updated successfully.")
        return redirect("customerapp:customer-dashboard")

    context = {"job_request": job_request}
    return render(request, "customerapp/edit_job_request.html", context)


@login_required()
@role_required([User.Role.CUSTOMER])
def customer_request_detail(request, job_request_id):
    """View full details of a job request."""
    job_request = get_object_or_404(
        JobRequest.objects.select_related("service", "service__category"),
        pk=job_request_id,
        customer=request.user,
    )

    project = None
    if job_request.is_converted_to_project:
        project = (
            Project.objects.filter(job_request=job_request)
            .select_related("technician")
            .first()
        )

    included_items = []
    service_item_mappings = ServiceItemMapping.objects.select_related("item").filter(
        service=job_request.service,
        item__is_available=True,
    )

    for mapping in service_item_mappings:
        quantity = mapping.quantity or 1
        unit_cost = mapping.item.unit_cost
        catalog_value = quantity * unit_cost
        included_price = mapping.extra_cost

        included_items.append(
            {
                "mapping": mapping,
                "quantity": quantity,
                "unit_cost": unit_cost,
                "catalog_value": catalog_value,
                "included_price": included_price,
            }
        )

    context = {
        "job_request": job_request,
        "project": project,
        "included_items": included_items,
    }
    return render(request, "customerapp/request_details.html", context)


@login_required()
@role_required([User.Role.CUSTOMER])
def customer_cancel_request(request, request_id):
    dashboard_url = reverse("customerapp:customer-dashboard") + "?tab=my-requests"
    """Cancel a job request that hasn't been converted to a project yet."""
    if request.method != "POST":
        return redirect(dashboard_url)

    job_request = get_object_or_404(JobRequest, pk=request_id, customer=request.user)

    if job_request.is_converted_to_project:
        messages.error(
            request,
            "This request has already been converted to a project and cannot be cancelled.",
        )
    else:
        log_details = _log_details(
            request,
            category=AuditLog.Category.BUSINESS,
            action="booking_cancelled",
            description=f"Job request #{job_request.pk} for '{job_request.service.title}' cancelled by {request.user.email}",
            target=job_request,
            metadata={"service_title": job_request.service.title},
        )
        job_request.delete()
        transaction.on_commit(lambda: record_audit_log_tasks.delay(log_details))  # type: ignore
        messages.success(request, "Job request cancelled successfully.")

    return redirect(dashboard_url)


@login_required()
@role_required([User.Role.CUSTOMER])
def customer_project_detail(request, project_id):
    """View complete project details with technician and admin contact information."""
    from django.conf import settings

    from .models import Feedback

    project = get_object_or_404(
        Project.objects.select_related("job_request__service__category", "technician"),
        pk=project_id,
        job_request__customer=request.user,
    )

    # Get technician profile if technician exists
    technician_profile = None
    if project.technician:
        technician_profile = (
            project.technician.technician_profile
            if hasattr(project.technician, "technician_profile")
            else None
        )

    # Get admin email from settings
    admin_email = getattr(settings, "VAPID_ADMIN_EMAIL", "admin@example.com")

    # Get all admins from database
    admins = User.objects.filter(role=User.Role.ADMIN)

    # Get project items (historical snapshot, not current service)
    project_items = project.project_items.all()  # type: ignore

    # Get extra materials added during execution
    extra_materials = project.extra_materials.all()  # type: ignore

    # Get existing feedback for this project
    existing_feedback = Feedback.objects.filter(
        project=project, customer=request.user
    ).first()

    context = {
        "project": project,
        "job_request": project.job_request,
        "technician": project.technician,
        "technician_profile": technician_profile,
        "admin_email": admin_email,
        "admins": admins,
        "project_items": project_items,
        "extra_materials": extra_materials,
        "existing_feedback": existing_feedback,
    }
    return render(request, "customerapp/project_detail.html", context)


@login_required()
@role_required([User.Role.CUSTOMER])
def customer_feedback(request, project_id):
    """Submit feedback for a completed project."""
    project = get_object_or_404(
        Project.objects.select_related("job_request__customer"),
        pk=project_id,
        job_request__customer=request.user,
        status=Project.Status.COMPLETED,
    )

    if request.method == "POST":
        rating = request.POST.get("rating")
        comments = request.POST.get("comments", "").strip()

        if not rating:
            messages.error(request, "Rating is required.")
            return redirect(
                "customerapp:customer-project-detail", project_id=project_id
            )

        from .models import Feedback

        log_details = _log_details(
            request,
            category=AuditLog.Category.BUSINESS,
            action="feedback_submitted",
            description=f"Feedback submitted for project #{project.pk} by {request.user.email}",
            target=project,
            metadata={"rating": rating, "comments": comments},
        )

        Feedback.objects.create(
            customer=request.user,
            project=project,
            rating=rating,
            comments=comments,
        )

        transaction.on_commit(lambda: record_audit_log_tasks.delay(log_details))  # type: ignore

        messages.success(request, "Thank you for your feedback!")
        return redirect("customerapp:customer-project-detail", project_id=project_id)

    context = {"project": project}
    return render(request, "customerapp/feedback_form.html", context)
