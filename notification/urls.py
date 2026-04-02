from django.urls import path

from . import views

urlpatterns = [
    path(
        "", 
        views.notification_list, 
        name="notification-list"
    ),
    path(
        "<int:notification_id>/read/", 
        views.mark_as_read, 
        name="mark-as-read"
    ),
    path(
        "mark-all-read/", 
        views.mark_all_read, 
        name="mark-all-read"
    ),
    path(
        "unread-count/", 
        views.unread_count_json, 
        name="unread-count"
    ),
    # Web Push
    path(
        "push/vapid-key/", 
        views.vapid_public_key, 
        name="vapid-public-key"
    ),
    path(
        "push/subscribe/", 
        views.save_push_subscription, 
        name="push-subscribe"
    ),
]
