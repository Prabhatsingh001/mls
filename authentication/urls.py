from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('register/', views.register, name='register'),
    path("activate/<uidb64>/<token>/", views.activate, name="activate"),
    path("resend-verification/<str:email>/",views.resend_verification_email,name="resend-verification-email"),
    path("forgot_password/", views.forgot_password, name="forgot_password"),
    path("reset_password/<uidb64>/<token>/", views.reset_password, name="reset_password"),
    path('login/', views.login, name='login'),
    path('logout/', views.logout, name='logout'),
    path('profile/', views.profile, name='profile'),
]