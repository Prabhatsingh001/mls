from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class AuditLog(models.Model):
    class Category(models.TextChoices):
        USER = "USER", "User"
        BUSINESS = "BUSINESS", "Business"
        ADMIN = "ADMIN", "Admin"
        PROJECT = "PROJECT", "Project"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )

    category = models.CharField(max_length=20, choices=Category.choices)
    action = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    # Generic target object (same pattern as notification app)
    content_type = models.ForeignKey(
        ContentType, null=True, blank=True, on_delete=models.SET_NULL
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey("content_type", "object_id")

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["category", "-created_at"]),
            models.Index(fields=["action", "-created_at"]),
            models.Index(fields=["actor", "-created_at"]),
        ]

    def __str__(self):
        actor_label = self.actor.email if self.actor else "System"
        return f"[{self.category}] {self.action} by {actor_label}"
