from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
import random
import string


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('phone_verified', True)
        extra_fields.setdefault('role', 'ADMIN')

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        TECHNICIAN = "TECH", "Technician"
        CUSTOMER = "CUST", "Customer"

    class SignupMethod(models.TextChoices):
        EMAIL = "email", "Email"
        PHONE = "phone", "Phone"

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=15, blank=True)
    role = models.CharField(max_length=10, choices=Role.choices, null=True, blank=True)
    signup_method = models.CharField(
        max_length=10, choices=SignupMethod.choices, default=SignupMethod.EMAIL
    )
    phone_verified = models.BooleanField(default=False)

    # Required fields for Django Admin/Auth
    is_active = models.BooleanField(default=False)  # Users must verify email/phone before becoming active
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']

    def __str__(self):
        return f"{self.full_name} ({self.email})"
    

class TechnicianProfile(models.Model):
    class VerificationStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"
        BLACKLISTED = "blacklisted", "Blacklisted"

    """Profile model for technicians, linked to the User model."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='technician_profile')
    skills = models.JSONField(default=list)  # List of skills/areas of expertise
    experience_years = models.PositiveIntegerField(default=0)
    address = models.CharField(max_length=255, blank=True)
    profile_picture = models.ImageField(upload_to='profile_pictures/', null=True, blank=True)
    aadhar_image = models.ImageField(upload_to='aadhar_images/', null=True, blank=True)
    verification_status = models.CharField(max_length=20, default=VerificationStatus.PENDING)  # pending, verified, rejected

    def get_verification_status_display(self):
        return self.VerificationStatus(self.verification_status).label

    def __str__(self):
        return f"Technician Profile for {self.user.full_name}"
    

class CustomerProfile(models.Model):
    """Profile model for customers, linked to the User model."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='customer_profile')

    def __str__(self):
        return f"Customer Profile for {self.user.full_name}"
    

class Address(models.Model):
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name='addresses')
    street = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100)
    is_primary = models.BooleanField(default=False)


class PhoneOTP(models.Model):
    """Stores OTP codes for phone number verification."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='phone_otps')
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"OTP for {self.user.phone_number} - {'Used' if self.is_used else 'Active'}"

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @property
    def is_valid(self):
        return not self.is_used and not self.is_expired

    @classmethod
    def generate_otp(cls, user, validity_minutes=10):
        """Generate a 6-digit OTP for the given user, invalidating any previous OTPs."""
        # Invalidate previous OTPs
        cls.objects.filter(user=user, is_used=False).update(is_used=True)

        otp_code = ''.join(random.choices(string.digits, k=6))
        otp = cls.objects.create(
            user=user,
            otp=otp_code,
            expires_at=timezone.now() + timezone.timedelta(minutes=validity_minutes),
        )
        return otp
