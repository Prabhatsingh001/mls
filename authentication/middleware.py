from django.shortcuts import redirect
from django.urls import reverse
from social_django.middleware import SocialAuthExceptionMiddleware
from social_core.exceptions import AuthForbidden, AuthCanceled, AuthFailed


class RoleRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        if request.user.is_authenticated:
            # Allow these URLs without role
            allowed_urls = [
                reverse("a:choose-role"),
                reverse("a:logout"),
                reverse("a:redirect-dashboard"),
            ]

            if not request.user.role and request.path not in allowed_urls:
                return redirect("a:choose-role")

        return self.get_response(request)


class CustomSocialAuthExceptionMiddleware(SocialAuthExceptionMiddleware):
    def get_message(self, request, exception):
        if isinstance(exception, AuthForbidden):
            return "Your account has been blocked. Please contact support."

        if isinstance(exception, AuthCanceled):
            return "Google login was cancelled."

        if isinstance(exception, AuthFailed):
            return "Authentication failed. Please try again."

        return super().get_message(request, exception)

    def get_redirect_uri(self, request, exception):
        if isinstance(exception, AuthForbidden):
            return reverse("a:account-blocked")

        if isinstance(exception, (AuthCanceled, AuthFailed)):
            return reverse("a:login")

        return super().get_redirect_uri(request, exception)
