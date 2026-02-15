from django.contrib import messages
from django.contrib.sites.shortcuts import get_current_site
from django.db import transaction
from django.shortcuts import render,redirect
from django.contrib.auth import (
    authenticate, 
    login as auth_login, 
    logout as auth_logout,
)
from django.contrib.auth.decorators import login_required
from .models import User
from .tokens import account_activation_token, password_reset_token
from .tasks import send_reset_password_email, password_reset_success_email
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.encoding import force_bytes, force_str


def home(request):
    if request.user.is_authenticated:
        return render(request, 'home.html', {'user': request.user})
    return render(request, 'home.html', {'user': None})


def register(request):
    allowed_roles = dict(User.Role.choices)
    # Exclude ADMIN from self-registration
    allowed_roles.pop(User.Role.ADMIN, None)

    if request.method == 'POST':
        email = request.POST['email']
        full_name = request.POST['full_name']
        password = request.POST['password']
        confirm_password = request.POST['confirm_password']
        role = request.POST.get('role', User.Role.CUSTOMER)

        if role not in allowed_roles:
            return render(request, 'register.html', {'error': 'Invalid role selected.', 'roles': allowed_roles.items()})

        if password != confirm_password:
            return render(request, 'register.html', {'error': 'Passwords do not match.', 'roles': allowed_roles.items()})
        
        if User.objects.filter(email=email).exists():
            return render(request, 'register.html', {'error': 'Email already exists.', 'roles': allowed_roles.items()})
        
        user = User(email=email, full_name=full_name, role=role)
        user.set_password(password)
        user.save()
        return redirect('a:login')
    return render(request, 'register.html', {'roles': allowed_roles.items()})


def login(request):
    if request.method == 'POST':
        email = request.POST['email']
        password = request.POST['password']

        user = authenticate(request, email=email, password=password)
        if user is not None:
            auth_login(request, user)
            return redirect('a:home')
        else:
            return render(request, 'login.html', {'error': 'Invalid email or password.'})
    return render(request, 'login.html')

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

@login_required()
def profile(request):
    return render(request, 'profile.html', {'user': request.user})

