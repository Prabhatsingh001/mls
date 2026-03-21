import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.sessions.models import Session
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from auditapp.models import AuditLog
from auditapp.utils import _log_details
from auditapp.tasks import record_audit_log_tasks
from authentication.decorators import role_required
from authentication.models import CustomerProfile, TechnicianProfile, User
from customerapp.models import Feedback
from services.models import (
    Category,
    JobRequest,
    Project,
    ProjectItem,
    Service,
    ServiceItem,
    ServiceItemMapping,
)

logger = logging.getLogger(__name__)


@login_required()
@role_required([User.Role.ADMIN])
def admin_dashboard(request):

    tab = request.GET.get("tab", "technicians")
    page_number = request.GET.get("page")

    context = {"tab": tab}

    # 🔹 Optimized Stats (Single Aggregation Query)
    stats = User.objects.aggregate(
        total_admins=Count("id", filter=Q(role=User.Role.ADMIN)),
        total_customers=Count("id", filter=Q(role=User.Role.CUSTOMER)),
        active_technicians=Count(
            "id", filter=Q(role=User.Role.TECHNICIAN, is_active=True)
        ),
        inactive_technicians=Count(
            "id", filter=Q(role=User.Role.TECHNICIAN, is_active=False)
        ),
        available_technicians=Count(
            "id",
            filter=Q(role=User.Role.TECHNICIAN, technician_profile__is_available=True),
        ),
    )

    stats["total_services"] = Service.objects.count()
    stats["total_jobs"] = Project.objects.count()

    context["stats"] = stats

    # 🔹 Load only selected tab data
    if tab == "technicians":
        technicians_qs = (
            User.objects.filter(role=User.Role.TECHNICIAN)
            .only(
                "id",
                "full_name",
                "email",
                "is_active",
                "date_joined",
                "technician_profile__verification_status",
                "technician_profile__is_available",
            )
            .order_by("-date_joined")
        )

        paginator = Paginator(technicians_qs, 10)
        context["technicians"] = paginator.get_page(page_number)

    elif tab == "services":
        services_qs = (
            Service.objects.select_related("category")
            .only(
                "id",
                "title",
                "description",
                "base_price",
                "is_active",
                "category__id",
                "category__name",
            )
            .order_by("category__name", "title")
        )

        paginator = Paginator(services_qs, 10)
        context["services"] = paginator.get_page(page_number)

        context["categories"] = Category.objects.only("id", "name").order_by("name")
        context["item_types"] = ServiceItem.ItemType.choices
        context["catalog_items"] = ServiceItem.objects.only(
            "id",
            "name",
            "item_type",
            "image",
            "description",
            "unit_cost",
            "is_available",
        ).order_by("name")

    elif tab == "users":
        users_qs = User.objects.only(
            "id", "full_name", "email", "role", "is_active", "date_joined"
        ).order_by("-date_joined")

        paginator = Paginator(users_qs, 10)
        context["users"] = paginator.get_page(page_number)

    elif tab == "requests":
        from services.models import JobRequest

        requests_qs = (
            JobRequest.objects.select_related("customer", "service__category")
            .only(
                "id",
                "customer__full_name",
                "service__title",
                "service__category__name",
                "is_reviewed",
                "is_converted_to_project",
                "created_at",
            )
            .filter(is_converted_to_project=False)
            .order_by("-created_at")
        )
        paginator = Paginator(requests_qs, 10)
        context["requests"] = paginator.get_page(page_number)

    elif tab == "jobs":
        status_filter = request.GET.get("status", "")
        jobs_qs = Project.objects.select_related(
            "job_request__customer",
            "job_request__service__category",
            "technician",
        ).order_by("-job_request__created_at")
        if status_filter and status_filter in Project.Status.values:
            jobs_qs = jobs_qs.filter(status=status_filter)
        paginator = Paginator(jobs_qs, 10)
        context["jobs"] = paginator.get_page(page_number)
        context["job_statuses"] = Project.Status.choices
        context["current_status"] = status_filter

    elif tab == "categories":
        categories_qs = Category.objects.only("id", "name", "description").order_by(
            "name"
        )
        paginator = Paginator(categories_qs, 10)
        context["categories"] = paginator.get_page(page_number)

    elif tab == "feedbacks":
        feedbacks_qs = Feedback.objects.select_related(
            "customer", "project__job_request__service", "project__technician"
        ).order_by("-created_at")
        paginator = Paginator(feedbacks_qs, 10)
        context["feedbacks"] = paginator.get_page(page_number)

    elif tab == "audit-trails":
        audit_qs = AuditLog.objects.select_related("actor").order_by("-created_at")

        category_filter = request.GET.get("category", "")
        if category_filter and category_filter in AuditLog.Category.values:
            audit_qs = audit_qs.filter(category=category_filter)

        actor_filter = request.GET.get("actor", "")
        if actor_filter:
            try:
                audit_qs = audit_qs.filter(actor_id=int(actor_filter))
            except (ValueError, TypeError):
                pass

        date_from = request.GET.get("date_from", "")
        date_to = request.GET.get("date_to", "")
        if date_from:
            audit_qs = audit_qs.filter(created_at__date__gte=date_from)
        if date_to:
            audit_qs = audit_qs.filter(created_at__date__lte=date_to)

        action_filter = request.GET.get("action", "")
        if action_filter:
            audit_qs = audit_qs.filter(action__icontains=action_filter)

        paginator = Paginator(audit_qs, 20)
        context["audit_logs"] = paginator.get_page(page_number)
        context["audit_categories"] = AuditLog.Category.choices
        context["current_category"] = category_filter
        context["current_actor"] = actor_filter
        context["current_date_from"] = date_from
        context["current_date_to"] = date_to
        context["current_action"] = action_filter
        context["all_users"] = User.objects.only("id", "full_name", "email").order_by(
            "full_name"
        )

    return render(request, "adminapp/admin.html", context)


def logout_user_sessions(user):
    sessions = Session.objects.filter(expire_date__gte=timezone.now())

    for session in sessions:
        data = session.get_decoded()
        if data.get("_auth_user_id") == str(user.id):
            session.delete()


@login_required()
@role_required([User.Role.ADMIN])
def admin_toggle_user_active(request, user_id):
    dashboard_url = reverse("adminapp:admin-dashboard") + "?tab=users"
    if request.method == "POST":
        target = get_object_or_404(User, pk=user_id)

        if target.pk == request.user.pk:
            messages.error(request, "You cannot deactivate your own account.")
        else:
            target.is_blocked = not target.is_blocked
            target.save()

            if target.is_blocked:
                logout_user_sessions(target)

            status = "activated" if not target.is_blocked else "deactivated"

            log_details = _log_details(
                request,
                category=AuditLog.Category.ADMIN,
                action="user_status_changed",
                description=f"Admin {request.user.email} {status} {target.email}'s account",
                target=target,
                metadata={"new_status": status},
            )
            transaction.on_commit(lambda: record_audit_log_tasks.delay(log_details))  # type: ignore

            messages.success(
                request, f"{target.full_name}'s account has been {status}."
            )

    return redirect(request.META.get("HTTP_REFERER", "")) or redirect(dashboard_url)


@login_required()
@role_required([User.Role.ADMIN])
def admin_make_admin(request, user_id):
    """Promote a user to admin role."""
    dashboard_url = reverse("adminapp:admin-dashboard") + "?tab=users"
    if request.method == "POST":
        target = get_object_or_404(User, pk=user_id)
        if target.role == User.Role.ADMIN:
            messages.info(request, f"{target.full_name} is already an admin.")
        else:
            target.role = User.Role.ADMIN
            target.is_staff = True
            target.save()
            log_details = _log_details(
                request,
                category=AuditLog.Category.ADMIN,
                action="user_promoted",
                description=f"Admin {request.user.email} promoted {target.email} to admin",
                target=target,
                metadata={"new_role": target.role},
            )
            transaction.on_commit(lambda: record_audit_log_tasks.delay(log_details))  # type: ignore
            messages.success(request, f"{target.full_name} has been promoted to Admin.")
    return redirect(request.META.get("HTTP_REFERER", "")) or redirect(dashboard_url)


@login_required()
@role_required([User.Role.ADMIN])
def admin_remove_admin(request, user_id):
    """Demote an admin to regular user role."""
    dashboard_url = reverse("adminapp:admin-dashboard") + "?tab=users"
    if request.method == "POST":
        target = get_object_or_404(User, pk=user_id)
        if target.is_superuser:
            messages.error(request, "You cannot demote a superuser.")
        if target.pk == request.user.pk:
            messages.error(request, "You cannot demote yourself from admin.")
        elif target.role != User.Role.ADMIN:
            messages.info(request, f"{target.full_name} is not an admin.")
        else:
            target.role = User.Role.CUSTOMER  # Default to customer role
            target.is_staff = False
            target.save()
            log_details = _log_details(
                request,
                category=AuditLog.Category.ADMIN,
                action="user_demoted",
                description=f"Admin {request.user.email} demoted {target.email} from admin",
                target=target,
                metadata={"old_role": User.Role.ADMIN, "new_role": target.role},
            )
            transaction.on_commit(lambda: record_audit_log_tasks.delay(log_details))  # type: ignore
            messages.success(
                request, f"{target.full_name} has been demoted from Admin."
            )
    return redirect(request.META.get("HTTP_REFERER", "")) or redirect(dashboard_url)


@login_required()
@role_required([User.Role.ADMIN])
def admin_create_category(request):
    dashboard_url = reverse("adminapp:admin-dashboard") + "?tab=categories"
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        if not name:
            messages.error(request, "Category name is required.")
            return redirect("adminapp:admin-dashboard")
        try:
            Category.objects.create(name=name, description=description)
            messages.success(request, f'Category "{name}" created successfully.')
        except Exception as e:
            messages.error(request, f"Failed to create category: {e}")
    return redirect(dashboard_url)


@login_required()
@role_required([User.Role.ADMIN])
def admin_edit_category(request, category_id):
    dashboard_url = reverse("adminapp:admin-dashboard") + "?tab=categories"
    category = get_object_or_404(Category, pk=category_id)
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        if not name:
            messages.error(request, "Category name is required.")
            return redirect(dashboard_url)
        try:
            category.name = name
            category.description = description
            category.save(update_fields=["name", "description"])
            messages.success(request, f'Category "{name}" updated successfully.')
        except Exception as e:
            messages.error(request, f"Failed to update category: {e}")
    return redirect(dashboard_url)


@login_required()
@role_required([User.Role.ADMIN])
def admin_delete_category(request, category_id):
    dashboard_url = reverse("adminapp:admin-dashboard") + "?tab=categories"
    if request.method == "POST":
        category = get_object_or_404(Category, pk=category_id)
        name = category.name
        try:
            log_details = _log_details(
                request,
                category=AuditLog.Category.ADMIN,
                action="category_deleted",
                description=f"Admin {request.user.email} deleted category '{name}'",
                metadata={"category_name": name},
            )
            category.delete()
            transaction.on_commit(lambda: record_audit_log_tasks.delay(log_details))  # type: ignore
            messages.success(request, f'Category "{name}" has been deleted.')
        except Exception as e:
            messages.error(request, f"Failed to delete category: {e}")
            return redirect(request.META.get("HTTP_REFERER", "")) or redirect(
                dashboard_url
            )
    return redirect(dashboard_url)


@login_required()
@role_required([User.Role.ADMIN])
def admin_create_service(request):
    """Create a new service under a category."""
    dashboard_url = reverse("adminapp:admin-dashboard") + "?tab=services"
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        base_price = request.POST.get("base_price", "").strip()
        category_id = request.POST.get("category", "")
        new_category = request.POST.get("new_category", "").strip()

        if not title or not base_price:
            messages.error(request, "Title and base price are required.")
            return redirect(dashboard_url)

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
            return redirect(dashboard_url)

        try:
            Service.objects.create(
                category=category,
                title=title,
                description=description,
                base_price=base_price,
                is_active=True,
            )
            log_details = _log_details(
                request,
                category=AuditLog.Category.ADMIN,
                action="service_created",
                description=f"Admin {request.user.email} created service '{title}'",
                metadata={"service_title": title, "base_price": str(base_price)},
            )
            transaction.on_commit(lambda: record_audit_log_tasks.delay(log_details))  # type: ignore
            messages.success(request, f'Service "{title}" created successfully.')
        except Exception as e:
            messages.error(request, f"Failed to create service: {e}")

    return redirect(dashboard_url)


@login_required()
@role_required([User.Role.ADMIN])
def admin_delete_service(request, service_id):
    """Delete a service."""
    dashboard_url = reverse("adminapp:admin-dashboard") + "?tab=services"
    if request.method == "POST":
        try:
            service = get_object_or_404(Service, pk=service_id)
            name = str(service)
            log_details = _log_details(
                request,
                category=AuditLog.Category.ADMIN,
                action="service_deleted",
                description=f"Admin {request.user.email} deleted service '{name}'",
                metadata={"service_title": name},
            )
            service.delete()
            transaction.on_commit(lambda: record_audit_log_tasks.delay(log_details))  # type: ignore
            messages.success(request, f'Service "{name}" has been deleted.')
        except Exception as e:
            messages.error(request, f"Failed to delete service: {e}")
            return redirect(request.META.get("HTTP_REFERER", "")) or redirect(
                dashboard_url
            )
    return redirect(dashboard_url)


@login_required()
@role_required([User.Role.ADMIN])
def admin_update_service(request, service_id):
    """Edit an existing service."""
    service = get_object_or_404(Service, pk=service_id)
    dashboard_url = reverse("adminapp:admin-dashboard") + "?tab=services"

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        base_price = request.POST.get("base_price", "").strip()
        category_id = request.POST.get("category", "")
        new_category = request.POST.get("new_category", "").strip()

        if not title or not base_price:
            messages.error(request, "Title and base price are required.")
            return redirect(dashboard_url)

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
            return redirect(dashboard_url)

        try:
            old_price = str(service.base_price)
            old_title = service.title
            service.category = category
            service.title = title
            service.description = description
            service.base_price = base_price
            service.save()

            audit_meta = {"old_title": old_title, "new_title": title}
            action = "service_edited"
            if old_price != str(base_price):
                action = "price_changed"
                audit_meta["old_price"] = old_price
                audit_meta["new_price"] = str(base_price)

            log_details = _log_details(
                request,
                category=AuditLog.Category.ADMIN,
                action=action,
                description=f"Admin {request.user.email} edited service '{title}'",
                target=service,
                metadata=audit_meta,
            )
            transaction.on_commit(lambda: record_audit_log_tasks.delay(log_details))  # type: ignore

            messages.success(request, f'Service "{title}" updated successfully.')
        except Exception as e:
            messages.error(request, f"Failed to update service: {e}")

    return redirect(dashboard_url)


@login_required()
@role_required([User.Role.ADMIN])
def admin_toggle_service(request, service_id):
    """Toggle a service's active status."""
    dashboard_url = reverse("adminapp:admin-dashboard") + "?tab=services"
    if request.method == "POST":
        service = get_object_or_404(Service, pk=service_id)
        service.is_active = not service.is_active
        service.save()
        status = "activated" if service.is_active else "deactivated"
        messages.success(request, f'Service "{service.title}" has been {status}.')
    return redirect(dashboard_url)


@login_required()
@role_required([User.Role.ADMIN])
def admin_manage_service_items(request, service_id):
    """Manage item mappings for a specific service and the item catalog."""
    service = get_object_or_404(
        Service.objects.select_related("category").prefetch_related(
            "included_items__item"
        ),
        pk=service_id,
    )

    context = {
        "service": service,
        "mappings": ServiceItemMapping.objects.filter(service=service)
        .select_related("item")
        .order_by("display_order", "id"),
        "catalog_items": ServiceItem.objects.order_by("name"),
        "item_types": ServiceItem.ItemType.choices,
    }
    return render(request, "adminapp/service_items_manage.html", context)


@login_required()
@role_required([User.Role.ADMIN])
def admin_create_service_item(request):
    """Create a reusable service item for tasks/materials/tools."""
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        item_type = request.POST.get("item_type", "").strip()
        unit_cost = request.POST.get("unit_cost", "").strip()
        description = request.POST.get("description", "").strip()
        image = request.FILES.get("image")

        if not name or not item_type or not unit_cost:
            messages.error(request, "Name, item type, and unit cost are required.")
        elif item_type not in ServiceItem.ItemType.values:
            messages.error(request, "Invalid item type selected.")
        else:
            try:
                ServiceItem.objects.create(
                    name=name,
                    item_type=item_type,
                    image=image,
                    unit_cost=unit_cost,
                    description=description,
                    is_available=True,
                )
                messages.success(request, f'Item "{name}" created successfully.')
            except Exception as e:
                messages.error(request, f"Failed to create service item: {e}")

    return redirect(request.META.get("HTTP_REFERER", "") or "adminapp:admin-dashboard")


@login_required()
@role_required([User.Role.ADMIN])
def admin_update_service_item(request, item_id):
    """Update a reusable service item."""
    item = get_object_or_404(ServiceItem, pk=item_id)

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        item_type = request.POST.get("item_type", "").strip()
        unit_cost = request.POST.get("unit_cost", "").strip()
        description = request.POST.get("description", "").strip()
        is_available = request.POST.get("is_available") == "on"
        remove_image = request.POST.get("remove_image") == "on"
        image = request.FILES.get("image")

        if not name or not item_type or not unit_cost:
            messages.error(request, "Name, item type, and unit cost are required.")
        elif item_type not in ServiceItem.ItemType.values:
            messages.error(request, "Invalid item type selected.")
        else:
            try:
                item.name = name
                item.item_type = item_type
                item.unit_cost = unit_cost
                item.description = description
                item.is_available = is_available
                if remove_image and item.image:
                    item.image.delete(save=False)
                if image:
                    if item.image:
                        item.image.delete(save=False)
                    item.image = image
                item.save()
                messages.success(request, f'Item "{item.name}" updated successfully.')
            except Exception as e:
                messages.error(request, f"Failed to update service item: {e}")

    return redirect(request.META.get("HTTP_REFERER", "") or "adminapp:admin-dashboard")


@login_required()
@role_required([User.Role.ADMIN])
def admin_add_service_item_mapping(request, service_id):
    """Attach an existing service item to a service with custom metadata."""
    service = get_object_or_404(Service, pk=service_id)

    if request.method == "POST":
        item_id = request.POST.get("item_id", "").strip()
        is_optional = request.POST.get("is_optional") == "on"
        extra_cost = request.POST.get("extra_cost", "").strip() or None

        try:
            quantity = int(request.POST.get("quantity", "1").strip() or "1")
            display_order = int(request.POST.get("display_order", "0").strip() or "0")
            if quantity < 1 or display_order < 0:
                raise ValueError
        except ValueError:
            messages.error(
                request,
                "Quantity must be at least 1 and display order cannot be negative.",
            )
            return redirect(
                "adminapp:admin-manage-service-items", service_id=service.pk
            )

        if not item_id:
            messages.error(request, "Please select an item to add.")
            return redirect(
                "adminapp:admin-manage-service-items", service_id=service.pk
            )

        item = get_object_or_404(ServiceItem, pk=item_id)

        try:
            mapping, created = ServiceItemMapping.objects.update_or_create(
                service=service,
                item=item,
                defaults={
                    "quantity": quantity,
                    "is_optional": is_optional,
                    "extra_cost": extra_cost,
                    "display_order": display_order,
                },
            )
            if created:
                messages.success(
                    request, f'Item "{mapping.item.name}" added to "{service.title}".'
                )
            else:
                messages.success(
                    request,
                    f'Item "{mapping.item.name}" was already linked and has been updated.',
                )
        except Exception as e:
            messages.error(request, f"Failed to add item to service: {e}")

    return redirect("adminapp:admin-manage-service-items", service_id=service.pk)


@login_required()
@role_required([User.Role.ADMIN])
def admin_update_service_item_mapping(request, mapping_id):
    """Update quantity/cost/order metadata for an item linked to a service."""
    mapping = get_object_or_404(
        ServiceItemMapping.objects.select_related("service", "item"), pk=mapping_id
    )

    if request.method == "POST":
        is_optional = request.POST.get("is_optional") == "on"
        extra_cost = request.POST.get("extra_cost", "").strip() or None
        try:
            quantity = int(request.POST.get("quantity", "1").strip() or "1")
            display_order = int(request.POST.get("display_order", "0").strip() or "0")
            if quantity < 1 or display_order < 0:
                raise ValueError
        except ValueError:
            messages.error(
                request,
                "Quantity must be at least 1 and display order cannot be negative.",
            )
            return redirect(
                "adminapp:admin-manage-service-items", service_id=mapping.service.pk
            )

        try:
            mapping.quantity = quantity
            mapping.is_optional = is_optional
            mapping.extra_cost = extra_cost
            mapping.display_order = display_order
            mapping.save()
            messages.success(
                request,
                f'Updated mapping for "{mapping.item.name}" in "{mapping.service.title}".',
            )
        except Exception as e:
            messages.error(request, f"Failed to update mapped item: {e}")

    return redirect(
        "adminapp:admin-manage-service-items", service_id=mapping.service.pk
    )


@login_required()
@role_required([User.Role.ADMIN])
def admin_remove_service_item_mapping(request, mapping_id):
    """Remove an item mapping from a service."""
    mapping = get_object_or_404(
        ServiceItemMapping.objects.select_related("service", "item"), pk=mapping_id
    )
    service_id = mapping.service.pk
    service_title = mapping.service.title

    if request.method == "POST":
        name = mapping.item.name
        try:
            mapping.delete()
            messages.success(
                request,
                f'Item "{name}" removed from "{service_title}".',
            )
        except Exception as e:
            messages.error(request, f"Failed to remove mapped item: {e}")

    return redirect("adminapp:admin-manage-service-items", service_id=service_id)


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
            .select_related("job_request__service__category", "job_request__customer")
            .order_by("-job_request__created_at")
        )

    if target_user.role == User.Role.CUSTOMER:
        cust_profile = CustomerProfile.objects.filter(user=target_user).first()
        context["cust_profile"] = cust_profile
        if cust_profile:
            context["addresses"] = cust_profile.addresses.all()  # type:ignore

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
            old_status = tech_profile.verification_status
            tech_profile.verification_status = new_status
            tech_profile.save(update_fields=["verification_status"])
            log_details = _log_details(
                request,
                category=AuditLog.Category.ADMIN,
                action="provider_status_changed",
                description=f"Admin {request.user.email} changed {target_user.full_name}'s status from {old_status} to {new_status}",
                target=target_user,
                metadata={"old_status": old_status, "new_status": new_status},
            )
            transaction.on_commit(lambda: record_audit_log_tasks.delay(log_details))  # type: ignore
            messages.success(
                request,
                f"{target_user.full_name}'s status updated to {tech_profile.get_verification_status_display()}.",
            )
        else:
            messages.error(request, "Invalid verification status.")
    return redirect("adminapp:admin-user-details", user_id=user_id)


@login_required()
@role_required([User.Role.ADMIN])
def admin_get_requested_service_details(request, job_request_id):
    """View details of a specific job request for review."""
    job_request = get_object_or_404(
        JobRequest.objects.select_related("customer", "service__category"),
        pk=job_request_id,
    )
    technicians = (
        User.objects.filter(
            role=User.Role.TECHNICIAN,
            technician_profile__verification_status=TechnicianProfile.VerificationStatus.VERIFIED,
            technician_profile__is_available=True,
            is_active=True,
        )
        .only("id", "full_name")
        .order_by("full_name")
    )
    # Check if already converted to a project
    project = Project.objects.filter(job_request=job_request).first()
    context = {
        "job_request": job_request,
        "technicians": technicians,
        "project": project,
    }
    return render(request, "adminapp/review_details.html", context)


@login_required()
@role_required([User.Role.ADMIN])
def admin_mark_request_reviewed(request, job_request_id):
    """Mark a job request as reviewed."""
    if request.method == "POST":
        job_request = get_object_or_404(JobRequest, pk=job_request_id)
        job_request.is_reviewed = True
        job_request.save(update_fields=["is_reviewed"])
        messages.success(request, f"Request #{job_request.pk} marked as reviewed.")
    return redirect("adminapp:admin-review-details", job_request_id=job_request_id)


@login_required()
@role_required([User.Role.ADMIN])
def admin_assign_technician(request, job_request_id):
    """Assign a technician to an existing project for this job request."""
    if request.method == "POST":
        job_request = get_object_or_404(JobRequest, pk=job_request_id)
        project = get_object_or_404(Project, job_request=job_request)
        technician_id = request.POST.get("technician_id", "")
        if technician_id:
            technician = get_object_or_404(
                User,
                pk=technician_id,
                role=User.Role.TECHNICIAN,
                technician_profile__verification_status=TechnicianProfile.VerificationStatus.VERIFIED,
                technician_profile__is_available=True,
                is_active=True,
            )
            project.technician = technician
            project.save(update_fields=["technician"])
            log_details = _log_details(
                request=request,
                category=AuditLog.Category.ADMIN,
                action="technician_assigned",
                description=f"Admin {request.user.email} assigned technician {technician.full_name} to project PRJ-{project.pk}",
                target=project,
                metadata={"technician_id": technician.pk, "project_id": project.pk},
            )
            transaction.on_commit(lambda: record_audit_log_tasks.delay(log_details))  # type: ignore
            messages.success(
                request,
                f"{technician.full_name} assigned to PRJ-{project.pk}.",
            )
        else:
            messages.error(request, "Please select a technician.")
    return redirect("adminapp:admin-review-details", job_request_id=job_request_id)


@login_required()
@role_required([User.Role.ADMIN])
def admin_convert_to_project(request, job_request_id):
    """Convert a reviewed job request into a project."""
    if request.method == "POST":
        job_request = get_object_or_404(JobRequest, pk=job_request_id)
        if hasattr(job_request, "project"):
            messages.info(
                request, "This request has already been converted to a project."
            )
            return redirect(
                "adminapp:admin-review-details", job_request_id=job_request_id
            )

        quoted_amount = request.POST.get("quoted_amount", "").strip()
        technician_id = request.POST.get("technician_id", "")
        start_date = request.POST.get("start_date", "").strip()
        notes = request.POST.get("notes", "").strip()

        if not quoted_amount:
            quoted_amount = job_request.service.base_price

        technician = None
        if technician_id:
            technician = get_object_or_404(
                User,
                pk=technician_id,
                role=User.Role.TECHNICIAN,
                technician_profile__verification_status=TechnicianProfile.VerificationStatus.VERIFIED,
                technician_profile__is_available=True,
                is_active=True,
            )

        if start_date:
            status = Project.Status.SCHEDULED
        else:
            status = Project.Status.PENDING

        project = Project.objects.create(
            job_request=job_request,
            technician=technician,
            quoted_amount=quoted_amount,
            status=status,
            notes=notes,
            start_date=start_date,
        )

        # Copy service items to project items for historical tracking
        service_items = (
            ServiceItemMapping.objects.select_related("item")
            .filter(service=job_request.service, item__is_available=True)
            .order_by("display_order")
        )

        for mapping in service_items:
            ProjectItem.objects.create(
                project=project,
                service_item=mapping.item,
                item_name=mapping.item.name,
                item_type=mapping.item.item_type,
                quantity=mapping.quantity,
                unit_cost=mapping.item.unit_cost,
                extra_cost=mapping.extra_cost,
                is_optional=mapping.is_optional,
                display_order=mapping.display_order,
            )

        job_request.is_converted_to_project = True
        job_request.save(update_fields=["is_converted_to_project"])
        log_details = _log_details(
            request=request,
            category=AuditLog.Category.ADMIN,
            action="request_converted_to_project",
            description=f"Admin {request.user.email} converted request #{job_request.pk} to project PRJ-{project.pk}",
            target=project,
            metadata={"job_request_id": job_request.pk, "project_id": project.pk},
        )
        transaction.on_commit(lambda: record_audit_log_tasks.delay(log_details))  # type: ignore
        messages.success(request, f"Request #{job_request.pk} converted to a project.")
    return redirect("adminapp:admin-review-details", job_request_id=job_request_id)


@login_required()
@role_required([User.Role.ADMIN])
def admin_update_project_status(request, project_id):
    """Update the status of an existing project."""
    # job_request_id = request.GET.get("job_request_id", "")
    if request.method == "POST":
        project = get_object_or_404(Project, pk=project_id)
        new_status = request.POST.get("status", "")
        valid_statuses = [c[0] for c in Project.Status.choices]
        if new_status in valid_statuses:
            update_fields = ["status"]
            project.status = new_status
            if new_status == Project.Status.ONGOING and not project.start_date:
                project.start_date = timezone.now().date()
                update_fields.append("start_date")
            if new_status == Project.Status.COMPLETED:
                project.completion_date = timezone.now().date()
                update_fields.append("completion_date")
                if not project.job_request.is_project_completed:
                    project.job_request.is_project_completed = True
                    project.job_request.save(update_fields=["is_project_completed"])
            elif project.job_request.is_project_completed:
                project.job_request.is_project_completed = False
                project.job_request.save(update_fields=["is_project_completed"])

            project.save(update_fields=update_fields)
            messages.success(
                request,
                f"Project PRJ-{project.pk} status updated to {project.get_status_display()}.",
            )
        else:
            messages.error(request, "Invalid project status.")
    return redirect(
        "adminapp:admin-review-details",
        job_request_id=project.job_request.pk,  # type: ignore
    )


@login_required()
@role_required([User.Role.ADMIN])
def admin_update_project_start_date(request, project_id):
    """Update the start date of an existing project."""
    if request.method == "POST":
        project = get_object_or_404(Project, pk=project_id)
        start_date = request.POST.get("start_date", "").strip()
        if start_date:
            project.start_date = start_date
            project.status = Project.Status.SCHEDULED
            project.save(update_fields=["start_date", "status"])
            messages.success(
                request,
                f"Project PRJ-{project.pk} start date updated to {project.start_date}.",
            )
        else:
            messages.error(request, "Invalid start date.")
    return redirect(
        "adminapp:admin-review-details",
        job_request_id=project.job_request.pk,  # type: ignore
    )
