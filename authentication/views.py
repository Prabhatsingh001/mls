from django.contrib import messages
from django.contrib.sites.shortcuts import get_current_site
from django.db import transaction
from django.shortcuts import get_object_or_404, render,redirect
from django.contrib.auth import (
    authenticate, 
    login as auth_login, 
    logout as auth_logout,
    update_session_auth_hash,
)
from django.contrib.auth.decorators import login_required
from .models import User, PhoneOTP
from .tokens import account_activation_token, password_reset_token
from .tasks import send_reset_password_email, password_reset_success_email, send_verification_mail
from django.utils.http import urlsafe_base64_decode
from django.utils.encoding import force_str
import logging

logger = logging.getLogger(__name__)


def index(request):
    return render(request, 'main.html')


@login_required()
def home(request):
    return render(request, 'home.html', {'user': request.user})


def register(request):
    allowed_roles = dict(User.Role.choices)
    # Exclude ADMIN from self-registration
    allowed_roles.pop(User.Role.ADMIN, None)

    if request.method == 'POST':
        full_name = request.POST['full_name']
        password = request.POST['password']
        confirm_password = request.POST['confirm_password']
        role = request.POST.get('role', User.Role.CUSTOMER)
        signup_method = request.POST.get('signup_method', 'email')

        if role not in allowed_roles:
            return render(request, 'register.html', {'error': 'Invalid role selected.', 'roles': allowed_roles.items()})

        if password != confirm_password:
            return render(request, 'register.html', {'error': 'Passwords do not match.', 'roles': allowed_roles.items()})

        if signup_method == 'phone':
            # --- Phone signup flow ---
            phone = request.POST.get('phone', '').strip()
            if not phone:
                return render(request, 'register.html', {'error': 'Phone number is required.', 'roles': allowed_roles.items()})

            if User.objects.filter(phone_number=phone).exists():
                return render(request, 'register.html', {'error': 'Phone number already registered.', 'roles': allowed_roles.items()})

            # Create user with a placeholder email (phone-based), inactive until OTP verified
            placeholder_email = f"phone_{phone.replace('+', '').replace(' ', '')}@placeholder.local"
            if User.objects.filter(email=placeholder_email).exists():
                return render(request, 'register.html', {'error': 'Phone number already registered.', 'roles': allowed_roles.items()})

            user = User(
                email=placeholder_email,
                full_name=full_name,
                phone_number=phone,
                role=role,
                signup_method=User.SignupMethod.PHONE,
            )
            user.set_password(password)
            user.save()

            # Generate OTP
            otp = PhoneOTP.generate_otp(user)
            # Log OTP to console (integrate SMS provider like Twilio for production)
            logger.info(f"[Phone OTP] OTP for {phone}: {otp.otp}")
            print(f"\n{'='*50}")
            print(f"  OTP for {phone}: {otp.otp}")
            print(f"{'='*50}\n")

            messages.success(request, 'Registration successful! Please enter the OTP sent to your phone.')
            return redirect('a:verify-phone-otp', user_id=user.pk)

        else:
            # --- Email signup flow (existing) ---
            email = request.POST.get('email', '').strip()
            if not email:
                return render(request, 'register.html', {'error': 'Email is required.', 'roles': allowed_roles.items()})

            if User.objects.filter(email=email).exists():
                return render(request, 'register.html', {'error': 'Email already exists.', 'roles': allowed_roles.items()})

            user = User(email=email, full_name=full_name, role=role, signup_method=User.SignupMethod.EMAIL)
            user.set_password(password)
            user.save()
            transaction.on_commit(lambda: send_verification_mail.delay(user.id))  # type: ignore
            messages.success(request, 'Registration successful! Please check your email to verify your account.')
            return redirect('a:resend-verification-email', email=email)

    return render(request, 'register.html', {'roles': allowed_roles.items()})

@login_required()
def choose_role(request):
    if request.method == "POST":
        role = request.POST.get("role")

        if role in User.Role.values:
            request.user.role = role
            request.user.save()
            return redirect("a:home")

    return render(request, "choose_role.html")



def login(request):
    if request.method == 'POST':
        login_method = request.POST.get('login_method', 'email')
        password = request.POST.get('password', '')

        if login_method == 'phone':
            phone = request.POST.get('phone', '').strip()
            if not phone:
                return render(request, 'login.html', {'error': 'Phone number is required.', 'active_tab': 'phone'})
            try:
                user_obj = User.objects.get(phone_number=phone)
            except User.DoesNotExist:
                return render(request, 'login.html', {'error': 'Invalid phone number or password.', 'active_tab': 'phone'})
            user = authenticate(request, email=user_obj.email, password=password)
        else:
            email = request.POST.get('email', '').strip()
            if not email:
                return render(request, 'login.html', {'error': 'Email is required.', 'active_tab': 'email'})
            user = authenticate(request, email=email, password=password)

        if user is not None:
            auth_login(request, user)
            return redirect('a:home')
        else:
            return render(request, 'login.html', {
                'error': 'Invalid credentials.',
                'active_tab': login_method,
            })
    return render(request, 'login.html', {'active_tab': 'email'})

def logout(request):
    if request.user.is_authenticated:
        auth_logout(request)
    return redirect('a:home')


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
            return redirect("a:forgot_password")
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
                return redirect("a:reset_password", uidb64=uidb64, token=token)

            user.set_password(new_password)
            user.save()
            transaction.on_commit(lambda: password_reset_success_email.delay(user.id))  # type: ignore
            messages.success(request, "Password reset successfully")
            return redirect("a:login")
        return render(request, "reset_password.html", {"user": user})
    else:
        messages.error(request, "Password reset link is invalid or has expired")
        return redirect("a:login")

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
        user.save()
        messages.success(request, "Email verified successfully")
        return redirect("a:login")
    else:
        messages.error(request, "Email verification failed")
        return redirect("a:login")

@login_required()
def profile(request, user_id):
    return render(request, 'profile.html', {'user': request.user})

@login_required()
def edit_profile(request, user_id):
    user = get_object_or_404(User, pk=user_id)

    # Only allow users to edit their own profile
    if request.user.pk != user.pk:
        messages.error(request, "You can only edit your own profile.")
        return redirect('a:profile', user_id=user.pk)

    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        address = request.POST.get('address', '').strip()

        if full_name:
            user.full_name = full_name

        # Phone-signup users can optionally add an email
        if user.signup_method == User.SignupMethod.PHONE:
            new_email = request.POST.get('email', '').strip()
            if new_email and new_email != user.email:
                if User.objects.filter(email=new_email).exclude(pk=user.pk).exists():
                    messages.error(request, 'That email is already in use.')
                    return render(request, 'edit_profile.html', {'user': user})
                user.email = new_email
        else:
            # Email-signup users can update their phone number
            user.phone_number = phone_number

        user.address = address
        user.save()
        messages.success(request, 'Profile updated successfully!')
        return redirect('a:profile', user_id=user.pk)

    return render(request, 'edit_profile.html', {'user': user})

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
        return redirect('a:profile', user_id=user.pk)
    if request.method == "POST":
        new_password = request.POST.get("password")
        confirm_password = request.POST.get("confirm-password")

        if new_password != confirm_password:
            messages.error(request, "Passwords do not match")
            return redirect("a:profile", user_id=user.pk)

        user.set_password(new_password)
        user.save()

        update_session_auth_hash(request, user)
        # send success email
        transaction.on_commit(lambda: password_reset_success_email.delay(user.id))  # type: ignore
        messages.success(request, "Password reset successfully")

        return redirect("a:profile", user_id=user.pk)

    return render(request, "profile_update_password.html", {"user": user})


def join_as_technician(request):
    """Static landing page encouraging technicians to sign up."""
    return render(request, 'join_as_technician.html')


def verify_phone_otp(request, user_id):
    """Verify phone number using OTP after phone-based registration.

    GET: Render OTP input form.
    POST: Validate submitted OTP. On success, activate the user account
    and redirect to login. On failure, show error and allow retry.
    """
    user = get_object_or_404(User, pk=user_id, signup_method=User.SignupMethod.PHONE)

    if user.is_active and user.phone_verified:
        messages.info(request, "Phone number is already verified.")
        return redirect("a:login")

    if request.method == "POST":
        otp_input = request.POST.get("otp", "").strip()

        if not otp_input:
            messages.error(request, "Please enter the OTP.")
            return render(request, "verify_phone_otp.html", {"user": user})

        # Find the latest valid OTP for this user
        otp_obj = PhoneOTP.objects.filter(
            user=user, otp=otp_input, is_used=False
        ).order_by("-created_at").first()

        if otp_obj is None or not otp_obj.is_valid:
            messages.error(request, "Invalid or expired OTP. Please try again or request a new one.")
            return render(request, "verify_phone_otp.html", {"user": user})

        # OTP is valid — activate account
        otp_obj.is_used = True
        otp_obj.save()

        user.is_active = True
        user.phone_verified = True
        user.save()

        messages.success(request, "Phone number verified successfully! You can now sign in.")
        return redirect("a:login")

    return render(request, "verify_phone_otp.html", {"user": user})


def resend_phone_otp(request, user_id):
    """Resend a new OTP to the user's phone number.

    Generates a fresh OTP (invalidating any previous ones) and redirects
    back to the OTP verification page.
    """
    user = get_object_or_404(User, pk=user_id, signup_method=User.SignupMethod.PHONE)

    if user.is_active and user.phone_verified:
        messages.info(request, "Phone number is already verified.")
        return redirect("a:login")

    otp = PhoneOTP.generate_otp(user)
    # Log OTP to console (integrate SMS provider for production)
    logger.info(f"[Phone OTP] OTP for {user.phone_number}: {otp.otp}")
    print(f"\n{'='*50}")
    print(f"  OTP for {user.phone_number}: {otp.otp}")
    print(f"{'='*50}\n")

    messages.success(request, "A new OTP has been sent to your phone number.")
    return redirect("a:verify-phone-otp", user_id=user.pk)

