from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from authentication.models import User


class Notification(models.Model):
    class Type(models.TextChoices):
        PAYMENT_RECEIVED = "payment_received"
        JOB_CREATED = "job_created"
        TECHNICIAN_ASSIGNED = "technician_assigned"
        JOB_COMPLETED = "job_completed"
        JOB_REMINDER = "job_reminder"
        NEW_REQUEST = "new_request"
        NEW_TECHNICIAN = "new_technician"
        PENDING_REMINDER = "pending_reminder"

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notifications"
    )
    type = models.CharField(max_length=50, choices=Type.choices)
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    # optional generic reference
    content_type = models.ForeignKey(
        ContentType, null=True, blank=True, on_delete=models.CASCADE
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey("content_type", "object_id")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.type} – {self.title}"


class PushSubscription(models.Model):
    """Stores Web Push API subscription info per user/browser."""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="push_subscriptions"
    )
    endpoint = models.URLField(max_length=500)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "endpoint")

    def __str__(self):
        return f"PushSub – {self.user.email} ({self.endpoint[:40]}…)"
