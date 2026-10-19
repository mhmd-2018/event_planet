"""
Service layer for results.

Business rules:
* Only the event owner may create/edit/publish results (also enforced by
  permission classes and owner-filtered querysets).
* Publishing is only allowed once the event is FINISHED.
* `publish_at` gates public visibility: the public API only returns results
  whose publish_at is set and in the past (supports scheduled publishing).
"""

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import PermissionDenied, ValidationError

from events.models import Event

from .models import Result


class ResultService:

    @staticmethod
    def publish(result: Result, user, publish_at=None) -> Result:
        event = result.event
        if event.owner_id != user.id:
            raise PermissionDenied("Only the event owner can publish results.")
        if event.status != Event.Status.FINISHED:
            raise ValidationError(
                {"event": "Results can only be published for finished events."}
            )

        when = timezone.now()
        if publish_at is not None:
            if isinstance(publish_at, str):
                parsed = parse_datetime(publish_at)
                if parsed is None:
                    raise ValidationError(
                        {"publish_at": "Invalid datetime; use ISO 8601."}
                    )
                publish_at = parsed
            if not timezone.is_aware(publish_at):
                publish_at = timezone.make_aware(publish_at)
            when = publish_at

        result.publish_at = when
        result.save(update_fields=["publish_at", "updated_at"])
        return result

    @staticmethod
    def publish_all(event: Event, user) -> int:
        """Publish every draft result of a finished event at once."""
        if event.owner_id != user.id:
            raise PermissionDenied("Only the event owner can publish results.")
        if event.status != Event.Status.FINISHED:
            raise ValidationError(
                {"event": "Results can only be published for finished events."}
            )
        return Result.objects.filter(event=event, publish_at__isnull=True).update(
            publish_at=timezone.now()
        )
