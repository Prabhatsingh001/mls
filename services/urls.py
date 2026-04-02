from django.urls import path

from . import views

urlpatterns = [
    path("join/", views.join_as_technician, name="join-as-technician"),
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
    path(
        "project/<int:project_id>/mark-completed/",
        views.project_completion,
        name="project-completion",
    ),
    path(
        "project/<int:project_id>/extra-materials/add/",
        views.add_project_extra_material,
        name="add-project-extra-material",
    ),
    path(
        "project/<int:project_id>/extra-materials/<int:extra_material_id>/update/",
        views.update_project_extra_material,
        name="update-project-extra-material",
    ),
    path(
        "project/<int:project_id>/extra-materials/<int:extra_material_id>/delete/",
        views.delete_project_extra_material,
        name="delete-project-extra-material",
    ),
]
