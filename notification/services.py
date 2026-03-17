from authentication.models import User

from .models import Notification


def create_notification(user, type, title, message, obj=None, user_id=None):
    """Create a single in-app notification. Pass either *user* or *user_id*."""
    if user_id is not None and user is None:
        user = User.objects.get(pk=user_id)
    if user is None:
        raise ValueError("Either user or user_id must be provided")
    notification = Notification.objects.create(
        user=user, type=type, title=title, message=message, content_object=obj
    )
    return notification


def notify_user(user, type, title, message, obj=None, user_id=None, send_push=True):
    """Create an in-app notification for one user and optionally trigger push."""
    notification = create_notification(
        user=user,
        user_id=user_id,
        type=type,
        title=title,
        message=message,
        obj=obj,
    )

    if send_push:
        from . import tasks as notification_tasks

        notification_tasks.send_user_push_task.delay(  # type: ignore[attr-defined]
            notification.user.pk, title, message
        )

    return notification


def notify_payment_received(user, amount=None, obj=None, user_id=None):
    """Notify a user after a successful payment event."""
    amount_text = f" of Rs. {amount}" if amount is not None else ""
    return notify_user(
        user=user,
        user_id=user_id,
        type=Notification.Type.PAYMENT_RECEIVED,
        title="Payment Received",
        message=f"Your payment{amount_text} was received successfully.",
        obj=obj,
    )


def notify_admins(type, title, message, obj=None):
    """
    Send an in-app notification to every active admin, then dispatch
    SMS and browser push as background Celery tasks.
    """
    admins = User.objects.filter(role=User.Role.ADMIN, is_active=True)
    notifications = []
    admin_ids = []
    for admin in admins:
        admin_ids.append(admin.pk)
        notifications.append(
            Notification(
                user=admin,
                type=type,
                title=title,
                message=message,
                content_type=(_ct(obj) if obj else None),
                object_id=obj.pk if obj else None,
            )
        )
    Notification.objects.bulk_create(notifications)

    # Fire-and-forget Celery tasks for external channels
    from .tasks import send_admin_push_task, send_admin_sms_task

    send_admin_sms_task.delay(admin_ids, title, message)  # type: ignore
    send_admin_push_task.delay(admin_ids, title, message)  # type: ignore

    return notifications


def _ct(obj):
    from django.contrib.contenttypes.models import ContentType

    return ContentType.objects.get_for_model(obj)
