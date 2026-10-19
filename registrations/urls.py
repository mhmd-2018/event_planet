from django.urls import path

from . import views

urlpatterns = [
    path(
        "events/<int:event_id>/register/",
        views.ParticipantRegisterView.as_view(),
        name="participant-register",
    ),
    path(
        "registrations/",
        views.MyRegistrationsView.as_view(),
        name="my-registrations",
    ),
    path(
        "registrations/<int:pk>/cancel/",
        views.CancelRegistrationView.as_view(),
        name="cancel-registration",
    ),
    path(
        "events/<int:event_id>/feedback/",
        views.ParticipantFeedbackView.as_view(),
        name="participant-feedback",
    ),
]
