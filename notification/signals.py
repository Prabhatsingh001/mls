from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from authentication.models import TechnicianProfile
from services.models import JobRequest, Project

from .models import Notification
from .services import notify_admins, notify_user


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


@receiver(post_save, sender=JobRequest)
def notify_customer_job_created(sender, instance, created, **kwargs):
    """Notify the customer when their request is submitted."""
    if not created:
        return
    notify_user(
        user=instance.customer,
        type=Notification.Type.JOB_CREATED,
        title="Your Request Was Submitted",
        message=(
            f"Your request for '{instance.service.title}' has been received. "
            f"We will notify you when a technician is assigned."
        ),
        obj=instance,
    )


@receiver(pre_save, sender=Project)
def cache_project_previous_state(sender, instance, **kwargs):
    """Store previous state so post_save can detect real transitions."""
    if not instance.pk:
        instance._previous_status = None
        instance._previous_technician_id = None
        return

    previous = (
        Project.objects.filter(pk=instance.pk).values("status", "technician_id").first()
    )
    instance._previous_status = previous["status"] if previous else None
    instance._previous_technician_id = previous["technician_id"] if previous else None


def _notify_assignment(instance: Project):
    """Notify customer and technician about a technician assignment."""
    if instance.technician is None:
        return

    technician_name = (
        instance.technician.full_name if instance.technician else "a technician"
    )
    service_title = instance.job_request.service.title

    notify_user(
        user=instance.job_request.customer,
        type=Notification.Type.TECHNICIAN_ASSIGNED,
        title="A Technician Has Been Assigned",
        message=(
            f"{technician_name} has been assigned to your request for "
            f"'{service_title}'."
        ),
        obj=instance,
    )

    notify_user(
        user=instance.technician,
        type=Notification.Type.TECHNICIAN_ASSIGNED,
        title="You Have a New Assignment",
        message=(f"You have been assigned to PRJ-{instance.pk} for '{service_title}'."),
        obj=instance,
    )


@receiver(post_save, sender=Project)
def notify_project_lifecycle(sender, instance, created, **kwargs):
    """Emit project lifecycle notifications only when state actually changes."""
    previous_status = getattr(instance, "_previous_status", None)
    previous_technician_id = getattr(instance, "_previous_technician_id", None)

    current_technician_id = instance.technician.pk if instance.technician else None

    if created and current_technician_id is not None:
        _notify_assignment(instance)

    technician_changed = (
        current_technician_id is not None
        and previous_technician_id != current_technician_id
    )
    if not created and technician_changed:
        _notify_assignment(instance)

    status_completed_now = (
        instance.status == Project.Status.COMPLETED
        and previous_status != Project.Status.COMPLETED
    )
    if status_completed_now:
        notify_user(
            user=instance.job_request.customer,
            type=Notification.Type.JOB_COMPLETED,
            title="Your Job Has Been Completed",
            message=(
                f"Your request for '{instance.job_request.service.title}' has been "
                f"marked as completed. Please review the work and provide feedback."
            ),
            obj=instance,
        )
