from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect


class BlockedUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and request.user.is_blocked:
            logout(request)
            messages.error(
                request, "Your account has been blocked. Please contact support."
            )
            return redirect("a:login")
        return self.get_response(request)
