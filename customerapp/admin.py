from django.contrib import admin
from .models import Feedback


# Register your models here.
@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("customer", "project", "rating", "comments", "created_at")
    list_filter = ("rating", "created_at")
    search_fields = ("customer__full_name", "project__id", "comments")
