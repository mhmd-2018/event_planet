from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Custom user with a global platform role.

    Core decision: a user has exactly ONE global role (`participant` or
    `organizer`). This role gates which API groups the user may call.
    Stage-level duties (speaker, judge, coach, ...) are decoupled from this
    global role and are modelled separately via `events.StageRole`, so the
    same human can be a participant on one stage and a judge on another.
    """

    class Roles(models.TextChoices):
        PARTICIPANT = "participant", "Participant"
        ORGANIZER = "organizer", "Organizer"

    role = models.CharField(
        max_length=20,
        choices=Roles.choices,
        default=Roles.PARTICIPANT,
        db_index=True,
        help_text="Global platform role controlling access to API groups.",
    )

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.username} ({self.role})"

    def has_role(self, role: str) -> bool:
        """Role check with superuser bypass (admins can use any API group)."""
        return self.is_superuser or self.role == role

    @property
    def is_organizer(self) -> bool:
        return self.has_role(self.Roles.ORGANIZER)

    @property
    def is_participant(self) -> bool:
        return self.has_role(self.Roles.PARTICIPANT)


class Profile(models.Model):
    """Optional display information attached to every user."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    full_name = models.CharField(max_length=150, blank=True)
    bio = models.TextField(blank=True)
    website = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"Profile of {self.user.username}"
