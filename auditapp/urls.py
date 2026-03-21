from django.urls import path
from . import views

urlpatterns = [
    path("log/<int:log_id>/", views.get_log_details, name="log-details"),
]
