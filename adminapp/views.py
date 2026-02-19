from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from authentication.decorators import role_required
from authentication.models import User
from services.models import Category, Service

import logging

logger = logging.getLogger(__name__)


@login_required
@role_required([User.Role.ADMIN])
def admin_dashboard(request):
    """Admin dashboard with tabs: technicians, services, users."""
    tab = request.GET.get("tab", "technicians")

    technicians = User.objects.filter(role=User.Role.TECHNICIAN).order_by("-date_joined")
    services = Service.objects.select_related("category").order_by("category__name", "title")
    categories = Category.objects.all().order_by("name")
    users = User.objects.all().order_by("-date_joined")

    stats = {
        "total_users": users.count(),
        "active_technicians": technicians.filter(is_active=True).count(),
        "inactive_technicians": technicians.filter(is_active=False).count(),
        "total_services": services.count(),
        "total_admins": users.filter(role=User.Role.ADMIN).count(),
    }

    return render(request, "adminapp/admin.html", {
        "tab": tab,
        "technicians": technicians,
        "services": services,
        "categories": categories,
        "users": users,
        "stats": stats,
    })


@login_required
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


@login_required
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


@login_required
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


@login_required
@role_required([User.Role.ADMIN])
def admin_delete_service(request, service_id):
    """Delete a service."""
    if request.method == "POST":
        service = get_object_or_404(Service, pk=service_id)
        name = str(service)
        service.delete()
        messages.success(request, f'Service "{name}" has been deleted.')
    return redirect("adminapp:admin-dashboard")


@login_required
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

