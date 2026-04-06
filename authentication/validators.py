from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from PIL import Image
# from .models import User


def validate_image_size(file):
    max_size = 10 * 1024 * 1024  # 10MB
    if file.size > max_size:
        raise ValidationError(_("Image file size should not exceed 10MB."))


def validate_image(file):
    try:
        img = Image.open(file)
        img.verify()
        if hasattr(file, "seek"):
            try:
                file.seek(0)
            except (AttributeError, OSError):
                pass
    except Exception:
        raise ValidationError(_("Invalid image file."))

# def validate_role(role, allowed_roles):
#     if role not in allowed_roles:
#         return "Invalid role selected."


# def validate_password(password, confirm_password):
#     if password != confirm_password:
#         return "Passwords do not match."


# def validate_phone(phone):
#     if not phone:
#         return "Phone number is required for phone signup."

#     if User.objects.filter(phone_number=phone).exists():
#         return "Phone number already registered."


# def validate_email(email):
#     if not email:
#         return "Email is required for email signup."

#     if User.objects.filter(email=email).exists():
#         return "Email already exists."
