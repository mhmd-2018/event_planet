import os
from datetime import timedelta
from pathlib import Path
from .base import *

def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}

def _env_list(name: str, default: str) -> list:
    """Comma-separated env var -> list. Tolerates quotes/extra spaces."""
    raw = os.getenv(name, default).strip().strip('"').strip("'")
    return [h.strip() for h in raw.split(",") if h.strip()]

SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-dev-only-key-change-me")
DEBUG = _env_bool("DEBUG", "false")

ALLOWED_HOSTS = _env_list("ALLOWED_HOSTS", "*")
# Hardened fallback: ALLOWED_HOSTS must NEVER end up empty. With DEBUG=false
# an empty list makes Django answer 400 (DisallowedHost) to every request,
# including http://127.0.0.1:8000 — the exact bug this guards against.
if not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["*"] if DEBUG else ["localhost", "127.0.0.1", "[::1]"]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    # Secure default: every view must opt in to public access explicitly.
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": (
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.getenv("JWT_ACCESS_MINUTES", "60"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.getenv("JWT_REFRESH_DAYS", "7"))),
    "SIGNING_KEY": os.getenv("JWT_SECRET", SECRET_KEY),
    "ALGORITHM": os.getenv("JWT_ALGORITHM", "HS256"),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "UPDATE_LAST_LOGIN": False,
}