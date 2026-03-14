from django.db.models.signals import post_save
from django.dispatch import receiver

from authentication.models import TechnicianProfile
from services.models import JobRequest

from .models import Notification
from .services import notify_admins


@receiver(post_save, sender=JobRequest)
def notify_admin_new_request(sender, instance, created, **kwargs):
    """Notify all admins when a customer submits a new job request."""
    if not created:
        return
    notify_admins(
        type=Notification.Type.NEW_REQUEST,
        title="New Service Request",
        message=(
            f"{instance.customer.full_name} submitted a request for "
            f"'{instance.service.title}' (preferred date: {instance.preferred_date})."
        ),
        obj=instance,
    )


@receiver(post_save, sender=TechnicianProfile)
def notify_admin_new_technician(sender, instance, created, **kwargs):
    """Notify all admins when a new technician joins the platform."""
    if not created:
        return
    notify_admins(
        type=Notification.Type.NEW_TECHNICIAN,
        title="New Technician Joined",
        message=(
            f"{instance.user.full_name} ({instance.user.email}) has registered as a "
            f"technician and is awaiting verification."
        ),
        obj=instance,
    )
