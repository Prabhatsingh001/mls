import logging
import random
import string

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import (
    authenticate,
    update_session_auth_hash,
)
from django.contrib.auth import (
    login as auth_login,
)
from django.contrib.auth import (
    logout as auth_logout,
)
from django.contrib.auth.decorators import login_required
from django.contrib.sites.shortcuts import get_current_site
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django_ratelimit.decorators import ratelimit
from auditapp.models import AuditLog
from auditapp.tasks import record_audit_log_tasks
from auditapp.utils import _log_details

from .models import (
    Address,
    ContactMessage,
    CustomerProfile,
    PhoneOTP,
    TechnicianProfile,
    User,
)
from .tasks import (
    password_reset_success_email,
    send_contact_message_email,
    send_phone_verification_sms,
    send_reset_password_email,
    send_verification_mail,
)
from .tokens import account_activation_token, password_reset_token

logger = logging.getLogger(__name__)


def index(request):
    if request.user.is_authenticated:
        return redirect("a:redirect-dashboard")
    return render(request, "main.html")


@login_required()
def redirect_dashboard(request):

    if request.user.role == User.Role.ADMIN:
        return redirect("adminapp:admin-dashboard")

    elif request.user.role == User.Role.TECHNICIAN:
        return redirect("services:tech-dashboard")

    elif request.user.role == User.Role.CUSTOMER:
        return redirect("customerapp:customer-dashboard")

    return redirect("a:choose-role")


def account_blocked(request):
    return render(request, "account_blocked.html")


def contact(request):
    form_name = ""
    form_email = ""
    form_message = ""
    form_phone_number = ""

    if request.user.is_authenticated:
        form_name = request.user.full_name or ""
        form_email = request.user.email or ""
        form_phone_number = request.user.phone_number or ""

    if request.method == "POST":
        form_name = request.POST.get("name", "").strip()
        form_email = request.POST.get("email", "").strip()
        form_message = request.POST.get("message", "").strip()
        form_phone_number = request.POST.get("phone_number", "").strip()

        if not (form_name and form_email and form_message):
            messages.error(request, "Please fill in your name, email, and message.")
            return redirect("a:contact")

        contact = ContactMessage.objects.create(
            name=form_name,
            email=form_email,
            phone_number=form_phone_number,
            msg=form_message,
        )

        transaction.on_commit(
            lambda: send_contact_message_email.delay(contact_message_id=contact.pk)  # type: ignore
        )
        messages.success(
            request,
            "Thanks for reaching out. Our support team will contact you soon.",
        )
        return redirect("a:contact")

    return render(
        request,
        "contact.html",
        {
            "form_name": form_name,
            "form_email": form_email,
            "form_message": form_message,
            "form_phone_number": form_phone_number,
        },
    )


def about(request):
    return render(request, "about.html")


def register(request):
    allowed_roles = dict(User.Role.choices)
    # Exclude ADMIN from self-registration
    allowed_roles.pop(User.Role.ADMIN, None)

    if request.method == "POST":
        full_name = request.POST["full_name"]
        password = request.POST["password"]
        confirm_password = request.POST["confirm_password"]
        role = request.POST.get("role", User.Role.CUSTOMER)
        signup_method = request.POST.get("signup_method", "email")

        if role not in allowed_roles:
            messages.error(request, "Invalid role selected.")
            return render(
                request,
                "register.html",
                {"roles": allowed_roles.items()},
            )

        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(
                request,
                "register.html",
                {"roles": allowed_roles.items()},
            )

        if signup_method == "phone":
            # --- Phone signup flow ---
            phone = request.POST.get("phone", "").strip()
            if not phone:
                messages.error(request, "Phone number is required for phone signup.")
                return render(
                    request,
                    "register.html",
                    {"roles": allowed_roles.items()},
                )

            if User.objects.filter(phone_number=phone).exists():
                return render(
                    request,
                    "register.html",
                    {
                        "error": "Phone number already registered.",
                        "roles": allowed_roles.items(),
                    },
                )

            # Create user with a placeholder email (phone-based), inactive until OTP verified
            placeholder_email = (
                f"phone_{phone.replace('+', '').replace(' ', '')}@placeholder.local"
            )
            if User.objects.filter(email=placeholder_email).exists():
                return render(
                    request,
                    "register.html",
                    {
                        "error": "Phone number already registered.",
                        "roles": allowed_roles.items(),
                    },
                )

            user = User(
                email=placeholder_email,
                full_name=full_name,
                phone_number=phone,
                role=role,
                signup_method=User.SignupMethod.PHONE,
            )
            user.set_password(password)
            user.save()

            log_details = _log_details(
                request,
                category=AuditLog.Category.USER,
                action="signup",
                description=f"New user registered: {user.email} (method: phone)",
                target=user,
                actor=user,
                metadata={"signup_method": "phone", "role": role},
            )

            transaction.on_commit(lambda: record_audit_log_tasks.delay(log_details))  # type: ignore
            # Generate OTP
            otp = PhoneOTP.generate_otp(user)

            if settings.DEBUG:
                logger.info(f"[Phone OTP] OTP for {phone}: {otp.otp}")
                print(f"\n{'=' * 50}")
                print(f"  OTP for {phone}: {otp.otp}")
                print(f"{'=' * 50}\n")
            else:
                transaction.on_commit(
                    lambda: send_phone_verification_sms.delay(user.pk, otp.otp)  # type: ignore
                )  # type: ignore

            messages.success(
                request,
                "Registration successful! Please enter the OTP sent to your phone.",
            )
            return redirect("a:verify-phone-otp", user_id=user.pk)

        else:
            # --- Email signup flow (existing) ---
            email = request.POST.get("email", "").strip()
            if not email:
                messages.error(request, "Email is required for email signup.")
                return render(
                    request,
                    "register.html",
                    {"roles": allowed_roles.items()},
                )

            if User.objects.filter(email=email).exists():
                messages.error(request, "Email already exists.")
                return render(
                    request,
                    "register.html",
                    {"roles": allowed_roles.items()},
                )

            user = User(
                email=email,
                full_name=full_name,
                role=role,
                signup_method=User.SignupMethod.EMAIL,
            )
            user.set_password(password)
            user.save()
            transaction.on_commit(lambda: send_verification_mail.delay(user.id))  # type: ignore

            log_details = _log_details(
                request,
                category=AuditLog.Category.USER,
                action="signup",
                description=f"New user registered: {user.email} (method: email)",
                target=user,
                actor=user,
                metadata={"signup_method": "email", "role": role},
            )
            transaction.on_commit(lambda: record_audit_log_tasks.delay(log_details))  # type: ignore

            messages.success(
                request,
                "Registration successful! Please check your email to verify your account.",
            )
            return redirect("a:resend-verification-email", email=email)

    return render(request, "register.html", {"roles": allowed_roles.items()})


@login_required()
def choose_role(request):
    if request.method == "POST":
        role = request.POST.get("role")

        if role in User.Role.values:
            user = request.user
            user.role = role
            user.save()

            if role == User.Role.CUSTOMER:
                CustomerProfile.objects.get_or_create(
                    user=user,
                    defaults={
                        "project_otp": "".join(random.choices(string.digits, k=6))
                    },
                )
            elif role == User.Role.TECHNICIAN:
                TechnicianProfile.objects.get_or_create(user=user)

            log_details = _log_details(
                request,
                category=AuditLog.Category.USER,
                action="role_change",
                description=f"User {request.user.email} changed role to {role}",
                target=request.user,
                metadata={"new_role": role},
            )
            transaction.on_commit(lambda: record_audit_log_tasks.delay(log_details))  # type: ignore
            return redirect("a:redirect-dashboard")

    return render(request, "choose_role.html")


def login(request):
    if request.method == "POST":
        login_method = request.POST.get("login_method", "email")
        password = request.POST.get("password", "")

        if login_method == "phone":
            phone = request.POST.get("phone", "").strip()
            if not phone:
                return render(
                    request,
                    "login.html",
                    {"error": "Phone number is required.", "active_tab": "phone"},
                )
            try:
                user_obj = User.objects.get(phone_number=phone)
            except User.DoesNotExist:
                return render(
                    request,
                    "login.html",
                    {
                        "error": "Invalid phone number or password.",
                        "active_tab": "phone",
                    },
                )
            user = authenticate(request, email=user_obj.email, password=password)
        else:
            email = request.POST.get("email", "").strip()
            if not email:
                return render(
                    request,
                    "login.html",
                    {"error": "Email is required.", "active_tab": "email"},
                )
            user = authenticate(request, email=email, password=password)

        if user is not None:
            auth_login(request, user)
            log_details = _log_details(
                request,
                category=AuditLog.Category.USER,
                action="login",
                description=f"User logged in: {user.email} (method: {login_method})",
                target=user,
                metadata={"login_method": login_method},
            )
            transaction.on_commit(lambda: record_audit_log_tasks.delay(log_details))  # type: ignore
            return redirect("a:redirect-dashboard")
        else:
            return render(
                request,
                "login.html",
                {
                    "error": "Invalid credentials.",
                    "active_tab": login_method,
                },
            )
    return render(request, "login.html", {"active_tab": "email"})


def logout(request):
    auth_logout(request)
    messages.success(request, "Logged out successfully.")
    return redirect("a:login")


def forgot_password(request):
    """Initiate a password reset by sending an email with a reset link.

    POST: Accepts an `email` field, looks up the user and schedules a
    `send_reset_password_email` task that will email a reset link containing a
    uid and token. Shows success or error messages and redirects to the
    appropriate page.

    GET: Render the "forgot password" form.
    """

    if request.method == "POST":
        email = request.POST.get("email")

        if not email:
            messages.error(request, "email is required to reset password")

        try:
            user = User.objects.get(email=email)
            protocol = "https" if request.is_secure() else "http"
            current_site = get_current_site(request)

            transaction.on_commit(
                lambda: send_reset_password_email.delay(  # type: ignore
                    user.id,  # type: ignore
                    protocol,
                    current_site.domain,
                )
            )

            messages.success(request, "Password reset email sent successfully")
            return redirect("a:login")
        except User.DoesNotExist:
            messages.error(request, "User with this email does not exist")
            return redirect("a:forgot-password")
    return render(request, "forgot_password.html")


def reset_password(request, uidb64, token):
    """Complete a password reset after following the emailed link.

    The link contains a base64-encoded user id (`uidb64`) and a `token`. If
    the token validates the user can set a new password. Upon success, a
    confirmation email is scheduled and the user is redirected to login.

    Args:
        request (HttpRequest): Django request object.
        uidb64 (str): Base64-encoded user id.
        token (str): Password reset token.

    Returns:
        HttpResponse: Render reset form or redirect after password reset.
    """

    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and password_reset_token.check_token(user, token):
        if request.method == "POST":
            new_password = request.POST.get("password")
            confirm_password = request.POST.get("confirm-password")

            if new_password != confirm_password:
                messages.error(request, "Passwords do not match")
                return redirect("a:reset-password", uidb64=uidb64, token=token)

            user.set_password(new_password)
            user.save()
            log_details = _log_details(
                request,
                category=AuditLog.Category.USER,
                action="password_reset",
                description=f"User {user.email} reset their password via email link",
                target=user,
                metadata={"user_id": user.pk},
            )
            transaction.on_commit(lambda: record_audit_log_tasks.delay(log_details))  # type: ignore
            transaction.on_commit(lambda: password_reset_success_email.delay(user.id))  # type: ignore
            messages.success(request, "Password reset successfully")
            return redirect("a:login")
        return render(request, "reset_password.html", {"user": user})
    else:
        messages.error(request, "Password reset link is invalid or has expired")
        return redirect("a:login")


@ratelimit(key="ip", rate="1/m", block=True)
def resend_verification_email(request, email=None):
    """Resend account verification email.

    POST: Look up the user by email and, if the account is not active, schedule
    a new verification email. Redirect and flash messages are used to notify
    the user of the result.

    GET: Render the resend verification page with an optional pre-filled
    `email` parameter.
    """

    if request.method == "POST":
        email = request.POST.get("email")
        user = get_object_or_404(User, email=email)

        if user.is_active:
            messages.success(request, "User is already verified!")
            return redirect("a:login")

        transaction.on_commit(lambda: send_verification_mail.delay(user.id))  # type: ignore
        messages.success(request, "Verification email has been resent!")
        return redirect("a:resend-verification-email", email=email)
    return render(request, "resend_verification_email.html", {"email": email})


def activate(request, uidb64, token):
    """Activate a user's account using a uid and token from email link.

    The `uidb64` is base64-encoded user id used together with a token to
    validate the request. On successful validation the account is activated
    and the user is redirected to the login page with a success message.

    Args:
        request (HttpRequest): Django request.
        uidb64 (str): Base64-encoded user id from the activation email.
        token (str): Activation token to validate the request.

    Returns:
        HttpResponse: Redirect to login with success/error message.
    """

    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and account_activation_token.check_token(user, token):
        user.is_active = True
        user.email_verified = True
        user.save()
        messages.success(request, "Email verified successfully")
        return redirect("a:login")
    else:
        messages.error(request, "Email verification failed")
        return redirect("a:login")


@login_required()
def profile(request, user_id):
    if request.user.pk != user_id:
        messages.error(request, "You can only view your own profile.")
        return redirect("a:profile", user_id=request.user.pk)
    user = request.user
    context = {"user": user}

    if user.role == User.Role.TECHNICIAN:
        tech_profile, _ = TechnicianProfile.objects.get_or_create(user=user)
        context["tech_profile"] = tech_profile
    elif user.role == User.Role.CUSTOMER:
        cust_profile, _ = CustomerProfile.objects.get_or_create(user=user)
        context["cust_profile"] = cust_profile
        context["addresses"] = cust_profile.addresses.all()  # type: ignore

    return render(request, "profile.html", context)


@login_required()
def edit_profile(request, user_id):
    user = get_object_or_404(User, pk=user_id)

    # Only allow users to edit their own profile
    if request.user.pk != user.pk:
        messages.error(request, "You can only edit your own profile.")
        return redirect("a:profile", user_id=user.pk)

    tech_profile = None
    cust_profile = None
    addresses = []

    if user.role == User.Role.TECHNICIAN:
        tech_profile, _ = TechnicianProfile.objects.get_or_create(user=user)
    elif user.role == User.Role.CUSTOMER:
        cust_profile, _ = CustomerProfile.objects.get_or_create(
            user=user,
            defaults={"project_otp": "".join(random.choices(string.digits, k=6))},
        )
        addresses = cust_profile.addresses.all()  # type: ignore

    if request.method == "POST":
        full_name = request.POST.get("full_name", "").strip()
        phone_number = request.POST.get("phone_number", "").strip()
        email_verification_required = False
        phone_verification_required = False

        if full_name:
            user.full_name = full_name

        # Phone-signup users can optionally add an email
        if user.signup_method == User.SignupMethod.PHONE:
            new_email = request.POST.get("email", "").strip()
            if new_email and new_email != user.email:
                if User.objects.filter(email=new_email).exclude(pk=user.pk).exists():
                    messages.error(request, "That email is already in use.")
                    return render(
                        request,
                        "edit_profile.html",
                        {
                            "user": user,
                            "tech_profile": tech_profile,
                            "cust_profile": cust_profile,
                            "addresses": addresses,
                        },
                    )
                user.email = new_email
                user.email_verified = False
                email_verification_required = True
        else:
            normalized_phone = phone_number.strip()
            if normalized_phone != user.phone_number:
                user.phone_number = normalized_phone
                user.phone_verified = False if normalized_phone else user.phone_verified
                phone_verification_required = bool(normalized_phone)

        user.save()

        if email_verification_required:
            transaction.on_commit(lambda: send_verification_mail.delay(user.id))  # type: ignore

        # Technician-specific fields
        if user.role == User.Role.TECHNICIAN and tech_profile:
            try:
                tech_profile.address = request.POST.get("address", "").strip()
                tech_profile.experience_years = int(
                    request.POST.get("experience_years", 0) or 0
                )
                skills_raw = request.POST.get("skills", "").strip()
                tech_profile.skills = (
                    [s.strip() for s in skills_raw.split(",") if s.strip()]
                    if skills_raw
                    else []
                )

                if "profile_picture" in request.FILES:
                    tech_profile.profile_picture = request.FILES["profile_picture"]
                if "aadhar_image" in request.FILES:
                    tech_profile.aadhar_image = request.FILES["aadhar_image"]
                tech_profile.full_clean()  # Validate image fields before saving
                tech_profile.save()
            except ValidationError as e:
                messages.error(request, f"Error updating profile: {e}")
                return render(
                    request,
                    "edit_profile.html",
                    {
                        "user": user,
                        "tech_profile": tech_profile,
                        "cust_profile": cust_profile,
                        "addresses": addresses,
                    },
                )

        # Customer address
        if user.role == User.Role.CUSTOMER and cust_profile:
            street = request.POST.get("street", "").strip()
            city = request.POST.get("city", "").strip()
            state = request.POST.get("state", "").strip()
            postal_code = request.POST.get("postal_code", "").strip()
            country = request.POST.get("country", "").strip()

            if street or city:
                primary_addr = cust_profile.addresses.filter(is_primary=True).first()  # type: ignore
                if primary_addr:
                    primary_addr.street = street
                    primary_addr.city = city
                    primary_addr.state = state
                    primary_addr.postal_code = postal_code
                    primary_addr.country = country
                    primary_addr.save()
                else:
                    Address.objects.create(
                        customer=cust_profile,
                        street=street,
                        city=city,
                        state=state,
                        postal_code=postal_code,
                        country=country,
                        is_primary=True,
                    )

        if phone_verification_required:
            otp = PhoneOTP.generate_otp(user)

            if settings.DEBUG:
                logger.info(f"[Phone OTP] OTP for {user.phone_number}: {otp.otp}")
                print(f"\n{'=' * 50}")
                print(f"  OTP for {user.phone_number}: {otp.otp}")
                print(f"{'=' * 50}\n")
            else:
                transaction.on_commit(
                    lambda: send_phone_verification_sms.delay(user.id, otp.otp)  # type: ignore
                )

            messages.success(
                request,
                "Phone number updated. Please verify with the OTP sent to your phone.",
            )
            return redirect(
                f"{reverse('a:verify-phone-otp', kwargs={'user_id': user.pk})}?next=profile"
            )

        if email_verification_required:
            messages.success(
                request,
                "Profile updated. A verification email has been sent to your email address.",
            )
        else:
            messages.success(request, "Profile updated successfully!")

        return redirect("a:profile", user_id=user.pk)

    return render(
        request,
        "edit_profile.html",
        {
            "user": user,
            "tech_profile": tech_profile,
            "cust_profile": cust_profile,
            "addresses": addresses,
        },
    )


@login_required()
def delete_account(request, user_id):
    user = get_object_or_404(User, pk=user_id)

    if request.user.pk != user.pk:
        messages.error(request, "You can only delete your own account.")
        return redirect("a:profile", user_id=user.pk)

    try:
        if request.method == "POST":
            auth_logout(request)
            user.delete()
            messages.success(request, "Your account has been deleted.")
            return redirect("a:login")
    except Exception as e:
        logger.error(f"Error deleting account for user {user.email}: {e}")
        messages.error(
            request,
            "An error occurred while deleting your account. Please try again later.",
        )
        return redirect("a:profile", user_id=user.pk)

    return render(request, "confirm_delete_account.html", {"user": user})


@login_required
def add_more_address(request, user_id):
    user = get_object_or_404(User, pk=user_id)

    if request.user.pk != user.pk:
        messages.error(request, "You can only edit your own profile.")
        return redirect("a:profile", user_id=user.pk)

    if user.role != User.Role.CUSTOMER:
        messages.error(request, "Only customers can have multiple addresses.")
        return redirect("a:profile", user_id=user.pk)

    cust_profile, _ = CustomerProfile.objects.get_or_create(user=user)

    if request.method == "POST":
        street = request.POST.get("street", "").strip()
        city = request.POST.get("city", "").strip()
        state = request.POST.get("state", "").strip()
        postal_code = request.POST.get("postal_code", "").strip()
        country = request.POST.get("country", "").strip()

        if not (street and city and state and postal_code and country):
            messages.error(request, "All address fields are required.")
            return redirect("a:profile", user_id=user.pk)

        Address.objects.create(
            customer=cust_profile,
            street=street,
            city=city,
            state=state,
            postal_code=postal_code,
            country=country,
            is_primary=False,
        )

        messages.success(request, "Address added successfully!")
        return redirect("a:profile", user_id=user.pk)

    return render(request, "add_address.html", {"user": user})


@login_required
def update_password(request, user_id):
    """Change a user's password while preserving the session.

    POST: Validate `password` and `confirm-password`, update the user's
    password and refresh the session auth hash so the user remains logged in.
    A success email is scheduled after the change.

    GET: Render the password update form.
    """

    user = get_object_or_404(User, id=user_id)
    if request.user.pk != user.pk:
        messages.error(request, "You can only change your own password.")
        return redirect("a:profile", user_id=user.pk)
    if request.method == "POST":
        new_password = request.POST.get("password")
        confirm_password = request.POST.get("confirm-password")

        if new_password != confirm_password:
            messages.error(request, "Passwords do not match")
            return redirect("a:profile", user_id=user.pk)

        user.set_password(new_password)
        user.save()

        log_details = _log_details(
            request,
            category=AuditLog.Category.USER,
            action="password_change",
            description=f"User {user.email} changed their password",
            target=user,
        )

        update_session_auth_hash(request, user)
        # send success email
        transaction.on_commit(lambda: record_audit_log_tasks.delay(log_details))  # type: ignore
        transaction.on_commit(lambda: password_reset_success_email.delay(user.id))  # type: ignore
        messages.success(request, "Password reset successfully")

        return redirect("a:profile", user_id=user.pk)

    return render(request, "profile_update_password.html", {"user": user})


def verify_phone_otp(request, user_id):
    """Verify phone number using OTP after phone-based registration.

    GET: Render OTP input form.
    POST: Validate submitted OTP. On success, activate the user account
    and redirect to login. On failure, show error and allow retry.
    """
    user = get_object_or_404(User, pk=user_id)
    return_to_profile = (
        request.GET.get("next") == "profile"
        and request.user.is_authenticated
        and request.user.pk == user.pk
    )

    if user.is_active and user.phone_verified:
        messages.info(request, "Phone number is already verified.")
        if return_to_profile:
            return redirect("a:profile", user_id=user.pk)
        return redirect("a:login")

    if not user.phone_number:
        messages.error(request, "No phone number found for verification.")
        if return_to_profile:
            return redirect("a:edit-profile", user_id=user.pk)
        return redirect("a:login")

    if request.method == "POST":
        otp_input = request.POST.get("otp", "").strip()

        if not otp_input:
            messages.error(request, "Please enter the OTP.")
            return render(
                request,
                "verify_phone_otp.html",
                {
                    "user": user,
                    "is_profile_verification": return_to_profile,
                },
            )

        # Find the latest valid OTP for this user
        otp_obj = (
            PhoneOTP.objects.filter(user=user, otp=otp_input, is_used=False)
            .order_by("-created_at")
            .first()
        )

        if otp_obj is None or not otp_obj.is_valid:
            messages.error(
                request,
                "Invalid or expired OTP. Please try again or request a new one.",
            )
            return render(
                request,
                "verify_phone_otp.html",
                {
                    "user": user,
                    "is_profile_verification": return_to_profile,
                },
            )

        # OTP is valid — activate account
        otp_obj.is_used = True
        otp_obj.save()

        user.is_active = True
        user.phone_verified = True
        user.save()

        if return_to_profile:
            messages.success(request, "Phone number verified successfully!")
            return redirect("a:profile", user_id=user.pk)

        messages.success(
            request, "Phone number verified successfully! You can now sign in."
        )
        return redirect("a:login")

    return render(
        request,
        "verify_phone_otp.html",
        {
            "user": user,
            "is_profile_verification": return_to_profile,
        },
    )


@ratelimit(key="ip", rate="1/m", block=True)
def resend_phone_otp(request, user_id):
    """Resend a new OTP to the user's phone number.

    Generates a fresh OTP (invalidating any previous ones) and redirects
    back to the OTP verification page.
    """
    user = get_object_or_404(User, pk=user_id)
    return_to_profile = (
        request.GET.get("next") == "profile"
        and request.user.is_authenticated
        and request.user.pk == user.pk
    )

    if user.is_active and user.phone_verified:
        messages.info(request, "Phone number is already verified.")
        if return_to_profile:
            return redirect("a:profile", user_id=user.pk)
        return redirect("a:login")

    if not user.phone_number:
        messages.error(request, "No phone number found for verification.")
        if return_to_profile:
            return redirect("a:edit-profile", user_id=user.pk)
        return redirect("a:login")

    otp = PhoneOTP.generate_otp(user)
    if settings.DEBUG:
        # Log OTP to console (integrate SMS provider for production)
        logger.info(f"[Phone OTP] OTP for {user.phone_number}: {otp.otp}")
        print(f"\n{'=' * 50}")
        print(f"  OTP for {user.phone_number}: {otp.otp}")
        print(f"{'=' * 50}\n")
    else:
        transaction.on_commit(
            lambda: send_phone_verification_sms.delay(user.id, otp.otp)  # type: ignore
        )

    messages.success(request, "A new OTP has been sent to your phone number.")
    if return_to_profile:
        return redirect(
            f"{reverse('a:verify-phone-otp', kwargs={'user_id': user.pk})}?next=profile"
        )
    return redirect("a:verify-phone-otp", user_id=user.pk)


# Error Handlers
def error_404(request, exception):
    """Custom 404 error handler."""
    return render(request, "error/404_error.html", status=404)


def error_403(request, exception):
    """Custom 403 error handler."""
    return render(request, "error/403_error.html", status=403)


def error_500(request):
    """Custom 500 error handler."""
    return render(request, "error/500_error.html", status=500)
