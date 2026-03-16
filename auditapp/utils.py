from django.contrib.contenttypes.models import ContentType

from .models import AuditLog


def get_client_ip(request):
    """Extract the client IP, respecting X-Forwarded-For behind a proxy."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_audit(
    request,
    category,
    action,
    description="",
    target=None,
    actor=None,
    metadata=None,
):
    """
    Create an audit log entry.

    Args:
        request:     The current HttpRequest (used for IP; can be None).
        category:    AuditLog.Category value (USER, BUSINESS, ADMIN).
        action:      Short action identifier string, e.g. "signup", "login".
        description: Human-readable description of what happened.
        target:      Optional Django model instance (the object acted upon).
        actor:       Optional User override. Defaults to request.user if authenticated.
        metadata:    Optional dict of extra data to store as JSON.
    """
    ip = get_client_ip(request) if request else None

    if (
        actor is None
        and request
        and hasattr(request, "user")
        and request.user.is_authenticated
    ):
        actor = request.user

    ct = None
    obj_id = None
    if target is not None:
        ct = ContentType.objects.get_for_model(target)
        obj_id = target.pk

    AuditLog.objects.create(
        actor=actor,
        category=category,
        action=action,
        description=description,
        content_type=ct,
        object_id=obj_id,
        ip_address=ip,
        metadata=metadata or {},
    )
