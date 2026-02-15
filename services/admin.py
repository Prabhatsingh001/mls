from django.contrib import admin
from .models import Category, Service, JobRequest, Project

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)} # Automatically fills slug based on name

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'base_price', 'is_active')
    list_filter = ('category', 'is_active')
    search_fields = ('title', 'description')
    list_editable = ('base_price', 'is_active') # Edit prices directly from the list view

class ProjectInline(admin.StackedInline):
    """Allows you to convert a Request to a Project directly on the same page"""
    model = Project
    extra = 0
    can_delete = False
    fields = ('technician', 'status', 'quoted_amount', 'start_date')

@admin.register(JobRequest)
class JobRequestAdmin(admin.ModelAdmin):
    list_display = ('customer', 'service', 'preferred_date', 'is_reviewed', 'is_converted_to_project')
    list_filter = ('is_reviewed', 'is_converted_to_project', 'service__category')
    search_fields = ('customer__full_name', 'customer__email', 'description')
    inlines = [ProjectInline] # This is powerful: assign a tech right inside the request!
    
    actions = ['mark_as_reviewed']

    def mark_as_reviewed(self, request, queryset):
        queryset.update(is_reviewed=True)
    mark_as_reviewed.short_description = "Mark selected requests as Reviewed" # type: ignore

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_service', 'get_customer', 'technician', 'status', 'quoted_amount')
    list_filter = ('status', 'technician', 'start_date')
    search_fields = ('id', 'source_request__customer__full_name', 'source_request__service__title')
    readonly_fields = ('source_request',) # Keep the link to the original lead locked
    
    # Custom methods to show related data in the list view
    def get_service(self, obj):
        return obj.source_request.service.title
    get_service.short_description = 'Service' # type: ignore

    def get_customer(self, obj):
        return obj.source_request.customer.full_name
    get_customer.short_description = 'Customer' # type: ignore

    # Color coding for status in the admin would require a custom template, 
    # but standard Django shows these clearly.