import base64
import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Notification, PushSubscription


@login_required
def notification_list(request):
    """Show all notifications for the logged-in user."""
    notifications = Notification.objects.filter(user=request.user)
    unread_count = notifications.filter(is_read=False).count()
    return render(
        request,
        "notification/list.html",
        {"notifications": notifications[:50], "unread_count": unread_count},
    )


@login_required
@require_POST
def mark_as_read(request, notification_id):
    """Mark a single notification as read."""
    notification = get_object_or_404(
        Notification, pk=notification_id, user=request.user
    )
    notification.is_read = True
    notification.save(update_fields=["is_read"])
    return redirect("notification:notification-list")


@login_required
@require_POST
def mark_all_read(request):
    """Mark every unread notification as read for the current user."""
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return redirect("notification:notification-list")


@login_required
def unread_count_json(request):
    """Return unread count as JSON (useful for AJAX badge refresh)."""
    count = Notification.objects.filter(user=request.user, is_read=False).count()
    return JsonResponse({"unread_count": count})


# ── Web Push endpoints ───────────────────────────────────────────────


@login_required
def vapid_public_key(request):
    """Return the VAPID public key as URL-safe base64 (applicationServerKey format)."""
    raw = settings.VAPID_PUBLIC_KEY
    if raw.startswith("-----BEGIN"):
        # PEM-encoded – extract the raw 65-byte EC point
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            PublicFormat,
            load_pem_public_key,
        )

        pub = load_pem_public_key(raw.encode())
        raw_bytes = pub.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
        raw = base64.urlsafe_b64encode(raw_bytes).rstrip(b"=").decode()
    return JsonResponse({"public_key": raw})


@login_required
@require_POST
def save_push_subscription(request):
    """Save or update a Web Push subscription for the logged-in user."""
    try:
        data = json.loads(request.body)
        endpoint = data["endpoint"]
        keys = data["keys"]
        PushSubscription.objects.update_or_create(
            user=request.user,
            endpoint=endpoint,
            defaults={
                "p256dh": keys["p256dh"],
                "auth": keys["auth"],
            },
        )
        return JsonResponse({"ok": True})
    except (KeyError, json.JSONDecodeError):
        return JsonResponse({"error": "Invalid payload"}, status=400)
