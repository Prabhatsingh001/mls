from social_core.exceptions import AuthForbidden
from django.db import transaction
from authentication.models import User


def check_user_not_blocked(strategy, backend, user=None, *args, **kwargs):
    if user and user.is_blocked:
        raise AuthForbidden(backend)


def get_or_create_user(strategy, details, backend, user=None, *args, **kwargs):

    if user:
        return {"user": user}

    email = details.get("email")
    if not email:
        return

    full_name = details.get("fullname") or details.get("first_name", "")

    with transaction.atomic():
        existing_user = User.objects.select_for_update().filter(email=email).first()

        if existing_user:
            if not existing_user.email_verified:
                existing_user.email_verified = True
                existing_user.is_active = True
                existing_user.save(update_fields=["email_verified", "is_active"])

            return {"user": existing_user}

        user = User.objects.create(
            email=email,
            full_name=full_name,
            signup_method=User.SignupMethod.GOOGLE,
            is_active=True,
            email_verified=True,
        )

    return {"user": user}
