"""Root URL configuration — every endpoint lives under /api/v1/ grouped by audience."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    # Auth: JWT obtain/refresh/verify + account registration + current user.
    path("api/v1/auth/", include("accounts.urls")),
    # Public, unauthenticated read-only API.
    path("api/v1/public/", include("events.urls_public")),
    path("api/v1/public/", include("results.urls_public")),
    # Participant API: register for events, own registrations, feedback.
    path("api/v1/participant/", include("registrations.urls")),
    # Organizer API: events, stages, stage roles, EAV attributes.
    path("api/v1/organizer/", include("events.urls_organizer")),
    # Organizer API: results management (also mounted under /organizer/).
    path("api/v1/organizer/", include("results.urls")),
]
