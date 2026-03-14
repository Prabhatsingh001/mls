from authentication.models import User

from .models import Notification


def create_notification(user, type, title, message, obj=None, user_id=None):
    """Create a single in-app notification. Pass either *user* or *user_id*."""
    if user_id is not None and user is None:
        user = User.objects.get(pk=user_id)
    notification = Notification.objects.create(
        user=user, type=type, title=title, message=message, content_object=obj
    )
    return notification


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

    send_admin_sms_task.delay(admin_ids, title, message)
    send_admin_push_task.delay(admin_ids, title, message)

    return notifications


def _ct(obj):
    from django.contrib.contenttypes.models import ContentType

    return ContentType.objects.get_for_model(obj)
