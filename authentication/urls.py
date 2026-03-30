from django.urls import path

from . import views

urlpatterns = [
    path("redirect-dashboard/", views.redirect_dashboard, name="redirect-dashboard"),
    path("account-blocked/", views.account_blocked, name="account-blocked"),
    path("contact/", views.contact, name="contact"),
    path("register/", views.register, name="register"),
    path("activate/<uidb64>/<token>/", views.activate, name="activate"),
    path(
        "resend-verification/<str:email>/",
        views.resend_verification_email,
        name="resend-verification-email",
    ),
    path(
        "verify-phone-otp/<int:user_id>/",
        views.verify_phone_otp,
        name="verify-phone-otp",
    ),
    path(
        "resend-phone-otp/<int:user_id>/",
        views.resend_phone_otp,
        name="resend-phone-otp",
    ),
    path("forgot_password/", views.forgot_password, name="forgot-password"),
    path(
        "reset_password/<uidb64>/<token>/", views.reset_password, name="reset-password"
    ),
    path("login/", views.login, name="login"),
    path("logout/", views.logout, name="logout"),
    path("profile/<int:user_id>/", views.profile, name="profile"),
    path("edit-profile/<int:user_id>/", views.edit_profile, name="edit-profile"),
    path(
        "add-address/<int:user_id>/",
        views.add_more_address,
        name="add-more-address",
    ),
    path(
        "update-password/<int:user_id>/", views.update_password, name="update-password"
    ),
    path("choose-role/", views.choose_role, name="choose-role"),
    path("delete-account/<int:user_id>/", views.delete_account, name="delete-account"),
]
