from django.urls import include, path, re_path

from .views import *

urlpatterns = [
    path('login/', LoginView.as_view(), name='account_login'),
    path('signup/', SignupView.as_view(), name='account_signup'),
    path("reauthenticate/", ReauthenticateView.as_view(), name="account_reauthenticate"),
    path("email/", EmailView.as_view(), name="account_email"),
    path('confirm-email/', verification_sent, name='account_verification_sent'),
    path('password/reset/', PasswordResetView.as_view(), name='account_reset_password'),
    path('password/reset/done/', password_reset_done, name='account_password_reset_done'),
    re_path(
        r"^password/reset/key/(?P<uidb36>[0-9A-Za-z]+)-(?P<key>.+)/$",
        PasswordResetFromKeyView.as_view(),
        name="account_reset_password_from_key",
    ),
    path('password/change/', PasswordChangeView.as_view(), name='account_password_change'),
    path('settings/two_factor_authentication_settings/', two_factor_authentication_settings, name='two_factor_authentication_settings'),
    path('login/code/confirm/', ConfirmLoginCodeView.as_view(), name='account_confirm_login_code'),
    path('totp/setup/', totp_setup, name='account_totp_setup'),
]

# Allauthのパターンを追加
allauth_patterns = [
    re_path(r'^', include('allauth.urls')),
]

urlpatterns += allauth_patterns
