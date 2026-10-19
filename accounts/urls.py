from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from .views import MeView, RegisterView, RoleTokenObtainPairView

urlpatterns = [
    # JWT
    path("token/", RoleTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("token/verify/", TokenVerifyView.as_view(), name="token_verify"),
    # Account
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("me/", MeView.as_view(), name="auth-me"),
]
