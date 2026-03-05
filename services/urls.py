from django.urls import path
from . import views

urlpatterns = [
    path("dashboard/", views.tech_dashboard, name="tech-dashboard"),
    path("join/", views.join_as_technician, name="join_as_technician"),
]
