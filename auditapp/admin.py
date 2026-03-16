from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "category", "action", "actor", "ip_address")
    list_filter = ("category", "action")
    search_fields = ("description", "actor__email", "actor__full_name")
    readonly_fields = ("created_at",)
