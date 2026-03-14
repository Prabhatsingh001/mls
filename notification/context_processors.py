from notification.models import Notification
from django.core.cache import cache


def unread_notifications(request):
    """Add unread notification count to every template context."""
    if request.user.is_authenticated:
        cache_key = f"unread_notification_count_{request.user.pk}"
        count = cache.get(cache_key)
        if count is None:
            count = Notification.objects.filter(
                user=request.user, is_read=False
            ).count()
            cache.set(cache_key, count, 60)
        return {"unread_notification_count": count}
    return {"unread_notification_count": 0}
