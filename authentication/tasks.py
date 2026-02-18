"""
Asynchronous Celery tasks for email notifications in the Auth application.

This module handles all email communications as background tasks using Celery,
ensuring that email sending doesn't block the main application flow. Each task:
- Supports both HTML and plain text email formats
- Uses Django templates for email content
- Handles failures silently to prevent user-facing errors
- Accepts IDs instead of model instances for better serialization

All tasks are registered with Celery using the @shared_task decorator for
flexibility in task queue configuration.
"""

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .tokens import account_activation_token, password_reset_token


@shared_task
def send_welcome_email(user_id):
    """
    Send a welcome email to newly registered users asynchronously.

    Args:
        user_id: UUID of the user to send the welcome email to

    The email includes:
        - Personalized greeting
        - Username and email confirmation
        - Login URL
        - Security notice for unintended recipients

    Both HTML and plain text versions are sent using the welcome_email.html template.
    """
    from .models import User
    user = User.objects.get(id=user_id)
    login_url = f"{settings.PROTOCOL}://{settings.SITE_DOMAIN}/a/login/"
    subject = "Welcome to URL.ly!!"
    html_content = render_to_string(
        "emails/welcome_email.html",
        {
            "user": user,
            "login_url": login_url,
        },
    )
    text_content = (
        f"Hi {user.full_name},\n\n"
        "Welcome to URL.ly!\n\n"
        f"Email: {user.email}\n\n"
        f"Login: {login_url}\n\n"
        "If you didn’t sign up, ignore this email.\n\n— URL.ly Team"
    )

    email = EmailMultiAlternatives(
        subject,
        text_content,
        settings.EMAIL_HOST_USER,
        [user.email],
    )
    email.attach_alternative(html_content, "text/html")
    email.send(fail_silently=True)


@shared_task
def send_verification_mail(user_id):
    """
    Send an email verification link to users asynchronously.

    Args:
        user_id: UUID of the user to send the verification email to

    The email includes:
        - Verification link with secure token
        - User-specific greeting
        - Instructions for verification
        - Security disclaimer

    Uses email_verification.html template and includes a time-sensitive
    verification token for secure email confirmation.
    """
    from .models import User

    user = User.objects.get(id=user_id)
    current_site = settings.SITE_DOMAIN
    protocol = settings.PROTOCOL
    subject = "Confirm your email - URL.LY"
    html_content = render_to_string(
        "emails/email_verification.html",
        {
            "user": user,
            "protocol": protocol,
            "domain": current_site,
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": account_activation_token.make_token(user),
        },
    )

    text_content = f"""
        Hello {user.full_name},

        Please confirm your email address by clicking the link below:
        {protocol}://{current_site}/a/activate/{urlsafe_base64_encode(force_bytes(user.pk))}/{account_activation_token.make_token(user)}/
        If you did not create an account, please ignore this email.

        Thank you for joining URL.LY!
    """

    email = EmailMultiAlternatives(
        subject,
        text_content,
        settings.EMAIL_HOST_USER,
        [user.email],
    )
    email.attach_alternative(html_content, "text/html")
    email.send(fail_silently=True)


@shared_task
def send_reset_password_email(
    user_id,
    protocol,
    current_site,
):
    """
    Send a password reset link to users asynchronously.

    Args:
        user_id: UUID of the user requesting password reset
        protocol: The protocol to use (http/https)
        current_site: The domain name for the reset link

    The email includes:
        - Password reset link with secure token
        - Security warning for unrequested resets
        - Instructions for password reset

    Uses reset_password_email.html template and includes a time-sensitive
    reset token for secure password reset process.
    """
    from .models import User
    user = User.objects.get(id=user_id)
    subject = "Reset Password"
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = password_reset_token.make_token(user)
    html_content = render_to_string(
        "emails/reset_password_email.html",
        {
            "user": user,
            "protocol": protocol,
            "domain": current_site,
            "uid": uid,
            "token": token,
        },
    )

    text_content = f"""
        Hello {user.full_name},
        You have requested to reset your password. Please click the link below to reset it:
        {protocol}://{current_site}/a/reset-password/{uid}/{token}/
        If you did not request this, please ignore this email.
        Thank you for using URL.LY!
    """

    email = EmailMultiAlternatives(
        subject,
        text_content,
        settings.EMAIL_HOST_USER,
        [user.email],
    )
    email.attach_alternative(html_content, "text/html")
    email.send(fail_silently=True)


@shared_task
def password_reset_success_email(user_id):
    """
    Send a confirmation email after successful password reset.

    Args:
        user_id: UUID of the user whose password was reset

    The email includes:
        - Confirmation of successful password reset
        - Login URL for immediate access
        - Security warning if change was not requested
        - Support contact information

    Uses password_reset_success_email.html template for consistent branding.
    """
    from .models import User
    user = User.objects.get(id=user_id)
    subject = "Password Reset Successfully"
    html_content = render_to_string(
        "emails/password_reset_success_email.html",
        {
            "user": user,
            "login_url": f"{settings.PROTOCOL}://{settings.SITE_DOMAIN}/a/login/",
        },
    )

    text_content = f"""
        Hi {user.full_name},
        Your password has been reset successfully. You can now log in with your new password.
        If you did not request this change, please contact support immediately.
        Thank you for using URL.LY!
    """
    email = EmailMultiAlternatives(
        subject,
        text_content,
        settings.EMAIL_HOST_USER,
        [user.email],
    )
    email.attach_alternative(html_content, "text/html")
    email.send(fail_silently=True)
