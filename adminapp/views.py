from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from authentication.decorators import role_required
from authentication.models import TechnicianProfile, CustomerProfile, Address, User
from services.models import Category, Service, Project
from django.core.paginator import Paginator
from django.db.models import Count, Q

import logging

logger = logging.getLogger(__name__)

@login_required()
@role_required([User.Role.ADMIN])
def admin_dashboard(request):

    tab = request.GET.get("tab", "technicians")
    page_number = request.GET.get("page")

    context = {"tab": tab}

    # 🔹 Optimized Stats (Single Aggregation Query)
    stats = User.objects.aggregate(
        total_users=Count("id"),
        total_admins=Count("id", filter=Q(role=User.Role.ADMIN)),
        active_technicians=Count("id", filter=Q(role=User.Role.TECHNICIAN, is_active=True)),
        inactive_technicians=Count("id", filter=Q(role=User.Role.TECHNICIAN, is_active=False)),
    )

    stats["total_services"] = Service.objects.count()

    context["stats"] = stats

    # 🔹 Load only selected tab data
    if tab == "technicians":
        technicians_qs = (
            User.objects
            .filter(role=User.Role.TECHNICIAN)
            .only("id", "full_name", "email", "is_active", "date_joined")
            .order_by("-date_joined")
        )

        paginator = Paginator(technicians_qs, 10)
        context["technicians"] = paginator.get_page(page_number)

    elif tab == "services":
        services_qs = (
            Service.objects
            .select_related("category")
            .only("id", "title", "category__name")
            .order_by("category__name", "title")
        )

        paginator = Paginator(services_qs, 10)
        context["services"] = paginator.get_page(page_number)

        context["categories"] = Category.objects.only("id", "name").order_by("name")

    elif tab == "users":
        users_qs = (
            User.objects
            .only("id", "full_name", "email", "role", "is_active", "date_joined")
            .order_by("-date_joined")
        )

        paginator = Paginator(users_qs, 10)
        context["users"] = paginator.get_page(page_number)

    elif tab == "requests":
        from services.models import JobRequest
        requests_qs = (
            JobRequest.objects
            .select_related("customer", "service__category")
            .only(
                "id", "customer__full_name", "service__title", "service__category__name",
                "is_reviewed", "is_converted_to_project", "created_at"
            )
            .order_by("-created_at")
        )
        paginator = Paginator(requests_qs, 10)
        context["requests"] = paginator.get_page(page_number)

    return render(request, "adminapp/admin.html", context)



@login_required()
@role_required([User.Role.ADMIN])
def admin_toggle_user_active(request, user_id):
    """Activate or deactivate a user account."""
    if request.method == "POST":
        target = get_object_or_404(User, pk=user_id)
        if target.pk == request.user.pk:
            messages.error(request, "You cannot deactivate your own account.")
        else:
            target.is_active = not target.is_active
            target.save()
            status = "activated" if target.is_active else "deactivated"
            messages.success(request, f"{target.full_name}'s account has been {status}.")
    return redirect(request.META.get("HTTP_REFERER", "")) or redirect("adminapp:admin-dashboard")


@login_required()
@role_required([User.Role.ADMIN])
def admin_make_admin(request, user_id):
    """Promote a user to admin role."""
    if request.method == "POST":
        target = get_object_or_404(User, pk=user_id)
        if target.role == User.Role.ADMIN:
            messages.info(request, f"{target.full_name} is already an admin.")
        else:
            target.role = User.Role.ADMIN
            target.is_staff = True
            target.save()
            messages.success(request, f"{target.full_name} has been promoted to Admin.")
    return redirect(request.META.get("HTTP_REFERER", "")) or redirect("adminapp:admin-dashboard")


@login_required()
@role_required([User.Role.ADMIN])
def admin_create_service(request):
    """Create a new service under a category."""
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        base_price = request.POST.get("base_price", "").strip()
        category_id = request.POST.get("category", "")
        new_category = request.POST.get("new_category", "").strip()

        if not title or not base_price:
            messages.error(request, "Title and base price are required.")
            return redirect("adminapp:admin-dashboard")

        # Resolve category
        if new_category:
            from django.utils.text import slugify
            slug = slugify(new_category)
            category, _ = Category.objects.get_or_create(
                slug=slug, defaults={"name": new_category}
            )
        elif category_id:
            category = get_object_or_404(Category, pk=category_id)
        else:
            messages.error(request, "Please select or enter a category.")
            return redirect("adminapp:admin-dashboard")

        try:
            Service.objects.create(
                category=category,
                title=title,
                description=description,
                base_price=base_price,
                is_active=True,
            )
            messages.success(request, f'Service "{title}" created successfully.')
        except Exception as e:
            messages.error(request, f"Failed to create service: {e}")

    return redirect("adminapp:admin-dashboard")


@login_required()
@role_required([User.Role.ADMIN])
def admin_delete_service(request, service_id):
    """Delete a service."""
    if request.method == "POST":
        service = get_object_or_404(Service, pk=service_id)
        name = str(service)
        service.delete()
        messages.success(request, f'Service "{name}" has been deleted.')
    return redirect("adminapp:admin-dashboard")


@login_required()
@role_required([User.Role.ADMIN])
def admin_edit_service(request, service_id):
    """Edit an existing service."""
    service = get_object_or_404(Service, pk=service_id)

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        base_price = request.POST.get("base_price", "").strip()
        category_id = request.POST.get("category", "")
        new_category = request.POST.get("new_category", "").strip()

        if not title or not base_price:
            messages.error(request, "Title and base price are required.")
            return redirect("adminapp:admin-dashboard")

        # Resolve category
        if new_category:
            from django.utils.text import slugify
            slug = slugify(new_category)
            category, _ = Category.objects.get_or_create(
                slug=slug, defaults={"name": new_category}
            )
        elif category_id:
            category = get_object_or_404(Category, pk=category_id)
        else:
            messages.error(request, "Please select or enter a category.")
            return redirect("adminapp:admin-dashboard")

        try:
            service.category = category
            service.title = title
            service.description = description
            service.base_price = base_price
            service.save()
            messages.success(request, f'Service "{title}" updated successfully.')
        except Exception as e:
            messages.error(request, f"Failed to update service: {e}")

    return redirect("adminapp:admin-dashboard")


@login_required()
@role_required([User.Role.ADMIN])
def admin_toggle_service(request, service_id):
    """Toggle a service's active status."""
    if request.method == "POST":
        service = get_object_or_404(Service, pk=service_id)
        service.is_active = not service.is_active
        service.save()
        status = "activated" if service.is_active else "deactivated"
        messages.success(request, f'Service "{service.title}" has been {status}.')
    return redirect("adminapp:admin-dashboard")


@login_required()
@role_required([User.Role.ADMIN])
def get_service_requests(request, service_id):
    """View all requests for a specific service."""
    service = get_object_or_404(Service, pk=service_id)
    requests_qs = service.requests.select_related("customer").only( # type: ignore
        "id", "customer__full_name", "status", "created_at"
    ).order_by("-created_at")

    paginator = Paginator(requests_qs, 10)
    page_number = request.GET.get("page")
    context = {
        "service": service,
        "requests": paginator.get_page(page_number),
    }
    return render(request, "adminapp/service_requests.html", context)


@login_required()
@role_required([User.Role.ADMIN])
def get_user_details(request, user_id):
    """View detailed information about a user."""
    target_user = get_object_or_404(User, pk=user_id)
    context: dict = {"target_user": target_user}

    if target_user.role == User.Role.TECHNICIAN:
        tech_profile = TechnicianProfile.objects.filter(user=target_user).first()
        context["tech_profile"] = tech_profile
        context["assigned_projects"] = (
            Project.objects.filter(technician=target_user)
            .select_related("source_request__service__category", "source_request__customer")
            .order_by("-source_request__created_at")
        )

    if target_user.role == User.Role.CUSTOMER:
        cust_profile = CustomerProfile.objects.filter(user=target_user).first()
        context["cust_profile"] = cust_profile
        if cust_profile:
            context["addresses"] = cust_profile.addresses.all() #type:ignore

    return render(request, "adminapp/user_details.html", context)


@login_required()
@role_required([User.Role.ADMIN])
def admin_update_tech_status(request, user_id):
    """Update a technician's verification status (verify / reject / blacklist)."""
    if request.method == "POST":
        target_user = get_object_or_404(User, pk=user_id, role=User.Role.TECHNICIAN)
        tech_profile = get_object_or_404(TechnicianProfile, user=target_user)
        new_status = request.POST.get("status", "")
        valid = [c[0] for c in TechnicianProfile.VerificationStatus.choices]
        if new_status in valid:
            tech_profile.verification_status = new_status
            tech_profile.save(update_fields=["verification_status"])
            messages.success(
                request,
                f"{target_user.full_name}'s status updated to {tech_profile.get_verification_status_display()}.",
            )
        else:
            messages.error(request, "Invalid verification status.")
    return redirect("adminapp:admin-user-details", user_id=user_id)


