from django.contrib import admin
from .models import User, TechnicianProfile, CustomerProfile, Address


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = (
        "email",
        "full_name",
        "role",
        "is_staff",
        "is_active",
        "phone_verified",
        "email_verified",
        "is_blocked",
    )
    list_filter = ("role", "is_staff", "is_active")
    search_fields = ("email", "full_name")
    ordering = ("email",)


@admin.register(TechnicianProfile)
class TechnicianProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "verification_status", "created_at")
    list_filter = ("verification_status",)
    search_fields = ("user__email", "user__full_name")
    ordering = ("-created_at",)


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at")
    search_fields = ("user__email", "user__full_name")
    ordering = ("-created_at",)


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("street", "city", "state", "postal_code")
    search_fields = (
        "user__email",
        "user__full_name",
        "street",
        "city",
        "state",
        "postal_code",
    )
    ordering = ("-created_at",)
