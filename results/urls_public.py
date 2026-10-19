from django.urls import path

from .views import PublicResultsView

urlpatterns = [
    path(
        "events/<int:event_id>/results/",
        PublicResultsView.as_view(),
        name="public-event-results",
    ),
]
