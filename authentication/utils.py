import os
from django.utils import timezone


def _generate_file_name(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        raise ValueError("Unsupported file extension.")
    timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
    return [f"MLS_{timestamp}", ext]


def user_profile_image_path(instance, filename):
    image_name, ext = _generate_file_name(instance, filename)
    return f"profile_pictures/{image_name}_profile{ext}"


def user_aadhar_image_path(instance, filename):
    image_name, ext = _generate_file_name(instance, filename)
    return f"aadhar_images/{image_name}_aadhar{ext}"