import logging

from django.conf import settings
from twilio.rest import Client

logger = logging.getLogger(__name__)


def send_sms(to, body):
    """
    Send a single SMS via Twilio.
    Returns the message SID on success, None on failure.
    """
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            body=body,
            from_=settings.TWILIO_PHONE_NUMBER,
            to=to,
        )
        logger.info("SMS sent to %s - SID %s", to, message.sid)
        return message.sid
    except Exception:
        logger.exception("Failed to send SMS to %s", to)
        return None
