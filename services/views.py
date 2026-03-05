from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from authentication.decorators import role_required
from authentication.models import User, TechnicianProfile
from .models import Project


@login_required()
@role_required([User.Role.TECHNICIAN])
def tech_dashboard(request):
    tech_profile, _ = TechnicianProfile.objects.get_or_create(user=request.user)

    assigned_projects = Project.objects.filter(technician=request.user).select_related(
        "source_request__service", "source_request__customer"
    )

    stats = {
        "active": assigned_projects.filter(
            status__in=[Project.Status.PENDING, Project.Status.SCHEDULED, Project.Status.ONGOING]
        ).count(),
        "completed": assigned_projects.filter(status=Project.Status.COMPLETED).count(),
        "total": assigned_projects.count(),
    }

    tab = request.GET.get("tab", "active")

    if tab == "completed":
        projects = assigned_projects.filter(status=Project.Status.COMPLETED).order_by("-completion_date")
    else:
        projects = assigned_projects.filter(
            status__in=[Project.Status.PENDING, Project.Status.SCHEDULED, Project.Status.ONGOING]
        ).order_by("-source_request__created_at")

    return render(request, "services/tech.html", {
        "tech_profile": tech_profile,
        "projects": projects,
        "stats": stats,
        "tab": tab,
    })


def join_as_technician(request):
    """Static landing page encouraging technicians to sign up."""
    return render(request, "join_as_technician.html")
