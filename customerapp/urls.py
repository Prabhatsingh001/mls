from django.urls import path
from . import views

urlpatterns = [
    path("", views.customer_dashboard, name="customer-dashboard"),
    path("create-request/", views.customer_create_request, name="customer-create-request"),
    path("cancel-request/<int:request_id>/", views.customer_cancel_request, name="customer-cancel-request"),
]
