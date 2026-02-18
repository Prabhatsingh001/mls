from django.dispatch import receiver
from django.db.models.signals import post_save
from .models import User
from django.db import transaction
from .tasks import send_welcome_email

@receiver(post_save, sender=User)
def send_email(sender, instance, created, **kwargs):
    """
    Send welcome email to newly registered users.

    Args:
        sender: The model class (User)
        instance: The actual User instance that was saved
        created: Boolean indicating if this is a new user
        **kwargs: Additional signal arguments

    This handler is triggered after user creation and sends a welcome
    email with login information and account details.
    """
    if created:
        transaction.on_commit(lambda: send_welcome_email.delay(instance.id))  # type: ignore