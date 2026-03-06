from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from authentication.decorators import role_required
from authentication.models import User
from services.models import Category, Service, JobRequest, Project


@login_required()
@role_required([User.Role.CUSTOMER])
def customer_dashboard(request):
    """Main customer dashboard with tabs: services, my-requests, my-projects."""
    tab = request.GET.get("tab", "services")

    # Stats
    my_requests = JobRequest.objects.filter(customer=request.user).select_related(
        "service", "service__category"
    )
    my_projects = Project.objects.filter(
        job_request__customer=request.user
    ).select_related("job_request__service", "technician")

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
    }

    context = {"tab": tab, "stats": stats}

    if tab == "services":
        categories = Category.objects.prefetch_related("services").all()
        context["categories"] = categories

    elif tab == "my-requests":
        context["requests"] = my_requests.exclude(
            is_converted_to_project=True
        ).order_by("-created_at")

    elif tab == "my-projects":
        context["projects"] = my_projects.order_by("-job_request__created_at")

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

    JobRequest.objects.create(
        customer=request.user,
        service=service,
        description=description,
        site_address=site_address,
        preferred_date=preferred_date,
    )

    messages.success(
        request, f"Job request for '{service.title}' submitted successfully!"
    )
    return redirect("customerapp:customer-dashboard")


@login_required()
@role_required([User.Role.CUSTOMER])
def customer_cancel_request(request, request_id):
    """Cancel a job request that hasn't been converted to a project yet."""
    if request.method != "POST":
        return redirect("customerapp:customer-dashboard")

    job_request = get_object_or_404(JobRequest, pk=request_id, customer=request.user)

    if job_request.is_converted_to_project:
        messages.error(
            request,
            "This request has already been converted to a project and cannot be cancelled.",
        )
    else:
        job_request.delete()
        messages.success(request, "Job request cancelled successfully.")

    return redirect("customerapp:customer-dashboard")
