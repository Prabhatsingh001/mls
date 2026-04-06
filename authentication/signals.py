import string
import random

from django.dispatch import receiver
from django.db.models.signals import post_save
from .models import CustomerProfile, User, TechnicianProfile
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
        if instance.signup_method == User.SignupMethod.PHONE:
            return  # Skip sending email for phone signups
        transaction.on_commit(lambda: send_welcome_email.delay(instance.id))  # type: ignore


@receiver(post_save, sender=User)
def create_profile(sender, instance, **kwargs):
    try:
        if instance.role == User.Role.CUSTOMER and not hasattr(
            instance, "customer_profile"
        ):
            otp_code = ''.join(random.choices(string.digits, k=6))
            CustomerProfile.objects.create(user=instance, project_otp=otp_code)

        elif instance.role == User.Role.TECHNICIAN and not hasattr(
            instance, "technician_profile"
        ):
            TechnicianProfile.objects.create(user=instance)

    except Exception as e:
        print(f"Error creating profile: {e}")