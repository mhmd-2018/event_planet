"""
Service layer for registrations and feedback.

Business rules enforced here (and additionally guarded by permissions):
* Registration is only possible for PUBLISHED events.
* Capacity (event level) is checked inside a transaction while holding a row
  lock on the event -> race-condition safe under PostgreSQL.
* Duplicate (event, participant) registrations are impossible (DB unique
  constraint + get_or_create + explicit active check).
* Feedback requires an ACTIVE registration and a FINISHED event.
"""

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from events.models import Event

from .models import Feedback, Registration


class RegistrationService:

    @staticmethod
    def register(participant, event_id):
        """
        Register a participant, re-activating a previously cancelled row.

        Returns (registration, created) where `created` is True when a new row
        was inserted (False for a re-activation).
        Raises ValidationError on duplicate/capacity/status violations.
        """
        with transaction.atomic():
            # Serialize concurrent registrations for this event on the event row.
            event = Event.objects.select_for_update().filter(pk=event_id).first()
            if event is None:
                raise NotFound("Event not found.")
            if event.status != Event.Status.PUBLISHED:
                raise ValidationError(
                    {"event": "Registration is only open for published events."}
                )

            registration, created = Registration.objects.get_or_create(
                event=event, participant=participant
            )
            if not created and registration.status == Registration.Status.ACTIVE:
                raise ValidationError(
                    {"detail": "You are already registered for this event."}
                )

            active_count = event.registrations.filter(
                status=Registration.Status.ACTIVE
            ).exclude(pk=registration.pk).count()
            if active_count >= event.capacity:
                raise ValidationError({"detail": "Event capacity has been reached."})

            if not created:
                registration.status = Registration.Status.ACTIVE
                registration.cancelled_at = None
                registration.save(update_fields=["status", "cancelled_at"])

        return registration, created

    @staticmethod
    def cancel(registration: Registration) -> Registration:
        if registration.status == Registration.Status.CANCELLED:
            raise ValidationError({"detail": "Registration is already cancelled."})
        if registration.event.status == Event.Status.FINISHED:
            raise ValidationError(
                {"event": "Cannot cancel a registration for a finished event."}
            )
        registration.status = Registration.Status.CANCELLED
        registration.cancelled_at = timezone.now()
        registration.save(update_fields=["status", "cancelled_at"])
        return registration


class FeedbackService:

    @staticmethod
    def submit_feedback(participant, event_id, rating: int, text: str) -> Feedback:
        """
        Submit (or update) feedback for a finished event.

        Core decision: feedback is an upsert — a participant has exactly one
        feedback row per event (DB unique constraint) and re-submitting
        updates rating/text.
        """
        event = Event.objects.filter(pk=event_id).first()
        if event is None:
            raise NotFound("Event not found.")
        if event.status != Event.Status.FINISHED:
            raise ValidationError(
                {"event": "Feedback is only accepted once the event is finished."}
            )
        is_registered = Registration.objects.filter(
            event=event,
            participant=participant,
            status=Registration.Status.ACTIVE,
        ).exists()
        if not is_registered:
            raise PermissionDenied("Only registered participants can submit feedback.")

        feedback, _ = Feedback.objects.update_or_create(
            event=event,
            participant=participant,
            defaults={"rating": rating, "text": text},
        )
        return feedback
