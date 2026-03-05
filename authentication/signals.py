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
def create_profile(sender, instance, created, **kwargs):
    """
    Create a user profile after a new user is created.

    Args:
        sender: The model class (User)
        instance: The actual User instance that was saved
        created: Boolean indicating if this is a new user
        **kwargs: Additional signal arguments
    This handler is triggered after user creation and can be used to
    create related profile models or perform additional setup.
    """
    if created:
        if instance.role == User.Role.CUSTOMER:
            CustomerProfile.objects.create(user=instance)
            
        if instance.role == User.Role.TECHNICIAN:
            TechnicianProfile.objects.create(user=instance)