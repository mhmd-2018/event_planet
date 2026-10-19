from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from events.models import Event


class Result(models.Model):
    """
    Flexible result row for an event.

    Core decision: a result targets EITHER a participant OR a team (given by
    name) — enforced by a DB check constraint. rank/score/notes are all
    optional so any scoring scheme fits. `publish_at` is NULL while the row
    is a draft; ResultService sets it when the owner publishes.
    """

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="results")
    participant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="results",
    )
    team_name = models.CharField(max_length=200, blank=True)
    rank = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
    score = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    notes = models.TextField(blank=True)
    publish_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="NULL = unpublished draft. Set by ResultService.publish().",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["rank", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(participant__isnull=False) | ~Q(team_name=""),
                name="result_has_participant_or_team",
            ),
        ]

    def __str__(self):
        target = self.participant.username if self.participant_id else self.team_name
        return f"{self.event.title}: {target or '?'}"

    @property
    def is_published(self) -> bool:
        return self.publish_at is not None
