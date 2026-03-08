from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from authentication.decorators import role_required
from authentication.models import TechnicianProfile, User

from .models import Project


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
def view_assignend_project_details(request, project_id):
    """View details of a specific project assigned to the technician."""
    try:
        project = Project.objects.select_related(
            "job_request__service", "job_request__customer"
        ).get(pk=project_id, technician=request.user)
    except Project.DoesNotExist:
        return render(request, "404.html", status=404)

    return render(request, "services/project_details.html", {"project": project})


def join_as_technician(request):
    """Static landing page encouraging technicians to sign up."""
    return render(request, "join_as_technician.html")


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
    project.save()

    label = dict(Project.Status.choices).get(new_status, new_status)
    messages.success(request, f"Project marked as {label}.")
    return redirect("services:project-details", project_id=project.pk)
