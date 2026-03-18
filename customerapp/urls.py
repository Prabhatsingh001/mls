from django.urls import path

from . import views

urlpatterns = [
    path("dashboard/", views.customer_dashboard, name="customer-dashboard"),
    path(
        "create-request/", views.customer_create_request, name="customer-create-request"
    ),
    path(
        "edit-request/<int:job_request_id>/",
        views.customer_edit_job_request,
        name="customer-edit-request",
    ),
    path(
        "request-detail/<int:job_request_id>/",
        views.customer_request_detail,
        name="customer-request-detail",
    ),
    path(
        "cancel-request/<int:request_id>/",
        views.customer_cancel_request,
        name="customer-cancel-request",
    ),
    path(
        "project/<int:project_id>/",
        views.customer_project_detail,
        name="customer-project-detail",
    ),
    path(
        "feedback/<int:project_id>/", views.customer_feedback, name="customer-feedback"
    ),
]
