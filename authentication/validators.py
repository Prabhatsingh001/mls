from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

def validate_image_size(file):
    max_size = 10 * 1024* 1024 # 10MB
    if file.size > max_size:
        raise ValidationError(_('Image file size should not exceed 10MB.'))
    