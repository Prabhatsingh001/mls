from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from services.models import Project


@receiver(post_save, sender=Project)
def generate_invoice_on_completion(sender, instance, created, **kwargs):
    """Generate invoice when project status changes to COMPLETED."""
    previous_status = getattr(instance, "_previous_status", None)

    status_payment_pending_now = (
        instance.status == Project.Status.PAYMENT_PENDING
        and previous_status != Project.Status.PAYMENT_PENDING
    )

    if not status_payment_pending_now:
        return

    # Check if invoice already exists
    if hasattr(instance, "invoice"):
        return

    # Use transaction.on_commit to ensure project is saved
    transaction.on_commit(lambda: _create_invoice_async(instance.pk))


def _create_invoice_async(project_id):
    """Create invoice asynchronously via Celery task."""
    from .tasks import create_invoice_task

    create_invoice_task.delay(project_id) # type: ignore
