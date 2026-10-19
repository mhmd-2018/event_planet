from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("events", views.OrganizerEventViewSet, basename="organizer-events")
router.register("attributes", views.AttributeViewSet, basename="attributes")

urlpatterns = [
    # Stages (nested under their event)
    path(
        "events/<int:event_pk>/stages/",
        views.OrganizerStageListCreateView.as_view(),
        name="organizer-stages-list",
    ),
    path(
        "events/<int:event_pk>/stages/<int:pk>/",
        views.OrganizerStageDetailView.as_view(),
        name="organizer-stages-detail",
    ),
    # Stage roles (nested under event + stage)
    path(
        "events/<int:event_pk>/stages/<int:stage_pk>/roles/",
        views.OrganizerStageRoleListCreateView.as_view(),
        name="organizer-stage-roles-list",
    ),
    path(
        "events/<int:event_pk>/stages/<int:stage_pk>/roles/<int:pk>/",
        views.OrganizerStageRoleDetailView.as_view(),
        name="organizer-stage-roles-detail",
    ),
    # EAV values bound to the event
    path(
        "events/<int:event_pk>/attribute-values/",
        views.OrganizerEventAttributeValueListCreateView.as_view(),
        name="organizer-attribute-values-list",
    ),
    path(
        "events/<int:event_pk>/attribute-values/<int:pk>/",
        views.OrganizerEventAttributeValueDetailView.as_view(),
        name="organizer-attribute-values-detail",
    ),
]

urlpatterns += router.urls
