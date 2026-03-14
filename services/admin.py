from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Category,
    JobRequest,
    Project,
    ProjectExtraMaterial,
    Service,
    ServiceItem,
    ServiceItemMapping,
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}  # Automatically fills slug based on name


@admin.register(ServiceItem)
class ServiceItemAdmin(admin.ModelAdmin):
    list_display = ("name", "image_preview", "item_type", "unit_cost", "is_available")
    list_filter = ("item_type", "is_available")
    search_fields = ("name", "description")
    list_editable = ("unit_cost", "is_available")
    readonly_fields = ("image_preview",)

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" alt="{}" style="height:40px;width:40px;object-fit:cover;border-radius:6px;"/>',
                obj.image.url,
                obj.name,
            )
        return "-"

    image_preview.short_description = "Image"  # type: ignore


class ServiceItemMappingInline(admin.TabularInline):
    """Manage which items (tasks/materials/tools) belong to a service."""

    model = ServiceItemMapping
    extra = 1
    fields = ("item", "quantity", "is_optional", "extra_cost", "display_order")
    autocomplete_fields = ("item",)
    ordering = ("display_order",)


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "base_price", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("title", "description")
    list_editable = (
        "base_price",
        "is_active",
    )  # Edit prices directly from the list view
    inlines = [ServiceItemMappingInline]


class ProjectInline(admin.StackedInline):
    """Allows you to convert a Request to a Project directly on the same page"""

    model = Project
    extra = 0
    can_delete = False
    fields = ("technician", "status", "quoted_amount", "start_date")


@admin.register(JobRequest)
class JobRequestAdmin(admin.ModelAdmin):
    list_display = (
        "customer",
        "service",
        "preferred_date",
        "is_reviewed",
        "is_converted_to_project",
    )
    list_filter = ("is_reviewed", "is_converted_to_project", "service__category")
    search_fields = ("customer__full_name", "customer__email", "description")
    inlines = [
        ProjectInline
    ]  # This is powerful: assign a tech right inside the request!

    actions = ["mark_as_reviewed"]

    def mark_as_reviewed(self, request, queryset):
        queryset.update(is_reviewed=True)

    mark_as_reviewed.short_description = "Mark selected requests as Reviewed"  # type: ignore


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "get_service",
        "get_customer",
        "technician",
        "status",
        "quoted_amount",
    )
    list_filter = ("status", "technician", "start_date")
    search_fields = (
        "id",
        "job_request__customer__full_name",
        "job_request__service__title",
    )
    readonly_fields = ("job_request",)  # Keep the link to the original lead locked

    # Custom methods to show related data in the list view
    def get_service(self, obj):
        return obj.job_request.service.title

    get_service.short_description = "Service"  # type: ignore

    def get_customer(self, obj):
        return obj.job_request.customer.full_name

    get_customer.short_description = "Customer"  # type: ignore

    # Color coding for status in the admin would require a custom template,
    # but standard Django shows these clearly.


@admin.register(ProjectExtraMaterial)
class ProjectExtraMaterialAdmin(admin.ModelAdmin):
    list_display = (
        "project",
        "material_name",
        "quantity",
        "unit_cost",
        "added_by",
        "created_at",
    )
    list_filter = ("created_at",)
    search_fields = (
        "material_name",
        "project__id",
        "project__job_request__service__title",
    )
    autocomplete_fields = ("project", "catalog_item", "added_by")
