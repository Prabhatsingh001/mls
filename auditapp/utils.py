from django.contrib.contenttypes.models import ContentType


def get_client_ip(request):
    """Extract the client IP, respecting X-Forwarded-For behind a proxy."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def get_content_type_for_model_instance(instance):
    """Helper to get ContentType for a given model instance."""
    return ContentType.objects.get_for_model(instance)


def _log_details(
    request,
    category,
    action,
    description,
    target=None,
    metadata=None,
    actor=None,
):
    if actor is None:
        actor = request.user.id
    else:
        actor = actor.id

    log_details = {
        "actor": actor,
        "category": category,
        "action": action,
        "description": description,
        "ip_address": get_client_ip(request),
        "metadata": metadata or {},
    }

    if target:
        ct = get_content_type_for_model_instance(target)

        log_details["content_type_id"] = ct.id  # Store the ContentType ID
        log_details["object_id"] = target.pk

    return log_details
