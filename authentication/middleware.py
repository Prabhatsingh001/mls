from django.shortcuts import redirect
from django.urls import reverse

class RoleRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            if not request.user.role:
                allowed_paths = [
                    reverse("a:choose-role"),
                    reverse("a:logout"),
                ]

                if request.path not in allowed_paths:
                    return redirect("a:choose-role")

        return self.get_response(request)
