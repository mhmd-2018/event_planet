from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from events.models import Event


class Registration(models.Model):
    """
    Event-level registration (core decision: never stage level).

    unique(event, participant) is enforced at the database. Cancelling does
    NOT delete the row — it flips the status to `cancelled`, which frees a
    capacity slot and can later be re-activated by registering again.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CANCELLED = "cancelled", "Cancelled"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="registrations")
    participant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="registrations",
    )
    registered_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-registered_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "participant"],
                name="unique_registration_per_event",
            ),
        ]

    def __str__(self):
        return f"{self.participant.username} @ {self.event.title} [{self.status}]"


class Feedback(models.Model):
    """Event rating submitted by a registered participant, only after finish."""

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="feedback")
    participant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="feedback_given",
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "participant"],
                name="unique_feedback_per_event",
            ),
            models.CheckConstraint(
                condition=Q(rating__gte=1, rating__lte=5),
                name="feedback_rating_1_to_5",
            ),
        ]

    def __str__(self):
        return f"{self.rating}/5 by {self.participant.username} @ {self.event.title}"
