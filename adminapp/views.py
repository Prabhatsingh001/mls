import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from authentication.decorators import role_required
from authentication.models import CustomerProfile, TechnicianProfile, User
from services.models import Category, JobRequest, Project, Service
from django.contrib.sessions.models import Session
from django.utils import timezone

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

            messages.success(
                request, f"{target.full_name}'s account has been {status}."
            )

    return redirect(request.META.get("HTTP_REFERER", "")) or redirect(
        "adminapp:admin-dashboard"
    )


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
    return redirect(request.META.get("HTTP_REFERER", "")) or redirect(
        "adminapp:admin-dashboard"
    )


@login_required()
@role_required([User.Role.ADMIN])
def admin_remove_admin(request, user_id):
    """Demote an admin to regular user role."""
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
            messages.success(
                request, f"{target.full_name} has been demoted from Admin."
            )
    return redirect(request.META.get("HTTP_REFERER", "")) or redirect(
        "adminapp:admin-dashboard"
    )


@login_required()
@role_required([User.Role.ADMIN])
def admin_create_category(request):
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
    return redirect("adminapp:admin-dashboard")


@login_required()
@role_required([User.Role.ADMIN])
def admin_edit_category(request, category_id):
    category = get_object_or_404(Category, pk=category_id)
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        if not name:
            messages.error(request, "Category name is required.")
            return redirect("adminapp:admin-dashboard")
        try:
            category.name = name
            category.description = description
            category.save(update_fields=["name", "description"])
            messages.success(request, f'Category "{name}" updated successfully.')
        except Exception as e:
            messages.error(request, f"Failed to update category: {e}")
    return redirect("adminapp:admin-dashboard")


@login_required()
@role_required([User.Role.ADMIN])
def admin_delete_category(request, category_id):
    if request.method == "POST":
        category = get_object_or_404(Category, pk=category_id)
        name = category.name
        try:
            category.delete()
            messages.success(request, f'Category "{name}" has been deleted.')
        except Exception as e:
            messages.error(request, f"Failed to delete category: {e}")
            return redirect(request.META.get("HTTP_REFERER", "")) or redirect(
                "adminapp:admin-dashboard"
            )
    return redirect("adminapp:admin-dashboard")


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
        try:
            service = get_object_or_404(Service, pk=service_id)
            name = str(service)
            service.delete()
            messages.success(request, f'Service "{name}" has been deleted.')
        except Exception as e:
            messages.error(request, f"Failed to delete service: {e}")
            return redirect(request.META.get("HTTP_REFERER", "")) or redirect(
                "adminapp:admin-dashboard"
            )
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
            tech_profile.verification_status = new_status
            tech_profile.save(update_fields=["verification_status"])
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

        Project.objects.create(
            job_request=job_request,
            technician=technician,
            quoted_amount=quoted_amount,
            status=status,
            notes=notes,
            start_date=start_date,
        )
        job_request.is_converted_to_project = True
        job_request.save(update_fields=["is_converted_to_project"])
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
            project.status = new_status
            project.save(update_fields=["status"])
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
