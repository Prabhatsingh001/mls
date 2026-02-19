from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.admin_dashboard, name='admin-dashboard'),
    path('toggle-active/<int:user_id>/', views.admin_toggle_user_active, name='admin-toggle-active'),
    path('make-admin/<int:user_id>/', views.admin_make_admin, name='admin-make-admin'),
    path('create-service/', views.admin_create_service, name='admin-create-service'),
    path('delete-service/<int:service_id>/', views.admin_delete_service, name='admin-delete-service'),
    path('toggle-service/<int:service_id>/', views.admin_toggle_service, name='admin-toggle-service'),
]
