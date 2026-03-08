from .models import Notification


def create_notification(user, type, title, message, obj=None):

    notification = Notification.objects.create(
        user=user, type=type, title=title, message=message, content_object=obj
    )

    return notification
