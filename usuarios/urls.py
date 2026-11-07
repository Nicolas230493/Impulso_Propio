from django.contrib.auth import views as auth_views
from django.urls import path

from .forms import LoginForm
from .views import RegistroView

urlpatterns = [
    path(
        "login/",
        auth_views.LoginView.as_view(authentication_form=LoginForm, redirect_authenticated_user=True),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("registro/", RegistroView.as_view(), name="registro"),
    path("password-reset/", auth_views.PasswordResetView.as_view(), name="password_reset"),
    path("password-reset/enviado/", auth_views.PasswordResetDoneView.as_view(), name="password_reset_done"),
    path(
        "password-reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path("password-reset/listo/", auth_views.PasswordResetCompleteView.as_view(), name="password_reset_complete"),
]
