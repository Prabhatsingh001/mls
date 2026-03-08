from django.urls import path

from . import views

urlpatterns = [
    path("dashboard/", views.tech_dashboard, name="tech-dashboard"),
    path(
        "toggle-availability/",
        views.technician_toggle_availability,
        name="toggle-availability",
    ),
    path(
        "project/<int:project_id>/",
        views.view_assignend_project_details,
        name="project-details",
    ),
    path(
        "project/<int:project_id>/update-status/",
        views.update_project_status,
        name="update-project-status",
    ),
    path("join/", views.join_as_technician, name="join_as_technician"),
]
