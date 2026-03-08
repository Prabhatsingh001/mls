from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from authentication.models import User


class Notification(models.Model):
    class Type(models.TextChoices):
        PAYMENT_RECEIVED = "payment_received"
        JOB_CREATED = "job_created"
        TECHNICIAN_ASSIGNED = "technician_assigned"
        JOB_COMPLETED = "job_completed"
        JOB_REMINDER = "job_reminder"

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
