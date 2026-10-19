from django.urls import path

from . import views

urlpatterns = [
    # NOTE: publish-all must come before the <int:pk> detail route.
    path(
        "events/<int:event_pk>/results/publish-all/",
        views.OrganizerResultViewSet.as_view({"post": "publish_all"}),
        name="organizer-results-publish-all",
    ),
    path(
        "events/<int:event_pk>/results/",
        views.OrganizerResultViewSet.as_view({"get": "list", "post": "create"}),
        name="organizer-results-list",
    ),
    path(
        "events/<int:event_pk>/results/<int:pk>/publish/",
        views.OrganizerResultViewSet.as_view({"post": "publish"}),
        name="organizer-results-publish",
    ),
    path(
        "events/<int:event_pk>/results/<int:pk>/",
        views.OrganizerResultViewSet.as_view(
            {"get": "retrieve", "put": "update", "patch": "partial_update", "delete": "destroy"}
        ),
        name="organizer-results-detail",
    ),
]
