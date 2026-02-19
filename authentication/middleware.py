from django.shortcuts import redirect
from django.urls import reverse

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
