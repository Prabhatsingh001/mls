import json
import logging
import re

from django.conf import settings
from pywebpush import WebPushException, webpush

logger = logging.getLogger(__name__)


def _normalized_vapid_private_key(raw_key: str) -> str:
    """Normalize key formats accepted in env variables for pywebpush.

    pywebpush/py_vapid expects either a key file path or a base64-encoded DER key
    string when a raw string is provided. If we receive a PEM string, strip
    header/footer and whitespace to get the DER base64 payload.
    """
    key = (raw_key or "").strip().replace("\\n", "\n")
    if key.startswith("-----BEGIN"):
        key = re.sub(r"-+BEGIN[^-]+-+|-+END[^-]+-+|\s+", "", key)
    return key


def send_push(subscription_queryset, title, body, url=None):
    """
    Send a browser push notification to every PushSubscription in *subscription_queryset*.
    """
    payload = json.dumps(
        {
            "title": title,
            "body": body,
            "url": url or "/notifications/",
        }
    )

    vapid_claims = {
        "sub": f"mailto:{settings.VAPID_ADMIN_EMAIL}",
    }
    vapid_private_key = _normalized_vapid_private_key(settings.VAPID_PRIVATE_KEY)

    for sub in subscription_queryset:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {
                        "p256dh": sub.p256dh,
                        "auth": sub.auth,
                    },
                },
                data=payload,
                vapid_private_key=vapid_private_key,
                vapid_claims=vapid_claims,  # type: ignore
            )
        except WebPushException as e:
            logger.warning("Push failed for %s: %s", sub.endpoint[:60], e)
            # 410 Gone means the subscription is stale — remove it
            if (
                hasattr(e, "response")
                and e.response is not None
                and e.response.status_code == 410
            ):
                sub.delete()
        except Exception:
            logger.exception("Unexpected push error for %s", sub.endpoint[:60])
