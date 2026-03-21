from django.db import transaction
from django.conf import settings
from .models import User

from authentication.models import PhoneOTP
from authentication.tasks import send_verification_mail, send_phone_verification_sms


def register_phone_user(full_name, password, phone, role):
    placeholder_email = (
        f"phone_{phone.replace('+', '').replace(' ', '')}@placeholder.local"
    )

    user = User.objects.create(
        email=placeholder_email,
        full_name=full_name,
        phone_number=phone,
        role=role,
        signup_method=User.SignupMethod.PHONE,
    )
    user.set_password(password)
    user.save()

    if not settings.DEBUG:
        otp = PhoneOTP.generate_otp(user)
        transaction.on_commit(
            lambda: send_phone_verification_sms.delay(user.pk, otp.otp)  # type: ignore
        )

    return user


def register_email_user(full_name, password, email, role):
    user = User.objects.create(
        email=email,
        full_name=full_name,
        role=role,
        signup_method=User.SignupMethod.EMAIL,
    )
    user.set_password(password)
    user.save()

    transaction.on_commit(lambda: send_verification_mail.delay(user.pk))  # type: ignore

    return user
