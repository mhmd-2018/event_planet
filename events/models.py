from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q


class Event(models.Model):
    """
    The central aggregate of the platform.

    Core decisions (documented in README):
    * Registration and capacity live at the EVENT level, not stage level.
    * The status may only be changed through ``EventService.change_status``
      — it is never writable directly through the API.
    * Lifecycle is strictly forward: draft -> published -> closed -> finished.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        CLOSED = "closed", "Closed"
        FINISHED = "finished", "Finished"

    TRANSITIONS = {
        Status.DRAFT: frozenset({Status.PUBLISHED}),
        Status.PUBLISHED: frozenset({Status.CLOSED}),
        Status.CLOSED: frozenset({Status.FINISHED}),
        Status.FINISHED: frozenset(),
    }

    # A "publicly visible" event is one that has been published at some point.
    # Drafts are never visible to the public API. Closed and finished events
    # remain visible so that results and the event record stay reachable.
    PUBLIC_STATUSES = (Status.PUBLISHED, Status.CLOSED, Status.FINISHED)

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    capacity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Maximum number of ACTIVE registrations (event level).",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="events",
        help_text="The organizer who owns the event; only they may edit it.",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_at__gt=F("start_at")),
                name="event_end_after_start",
            ),
        ]
        indexes = [models.Index(fields=["status", "start_at"])]

    def __str__(self):
        return f"{self.title} [{self.status}]"

    @property
    def active_registrations_count(self) -> int:
        # List viewsets annotate _active_registrations_count so they don't run
        # one COUNT(*) per row (N+1). Fall back to a live query everywhere else.
        annotated = self.__dict__.get("_active_registrations_count")
        if annotated is not None:
            return annotated
        # String literal avoids a circular import with the registrations app.
        return self.registrations.filter(status="active").count()

    @property
    def spots_left(self) -> int:
        return max(self.capacity - self.active_registrations_count, 0)

    @property
    def is_publicly_visible(self) -> bool:
        return self.status in self.PUBLIC_STATUSES

    def allowed_next_statuses(self):
        return [choice.value for choice in self.TRANSITIONS[self.status]]


class Stage(models.Model):
    """An ordered sub-part of an event (agenda item, round, session...)."""

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="stages")
    order = models.PositiveIntegerField(help_text="Order of the stage within the event.")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "order"],
                name="unique_stage_order_per_event",
            ),
            models.CheckConstraint(
                condition=Q(end_at__gt=F("start_at")),
                name="stage_end_after_start",
            ),
        ]

    def __str__(self):
        return f"{self.event.title} / #{self.order} {self.title}"


class StageRole(models.Model):
    """
    Assignment of a user to a stage-level duty. Stage roles are independent
    of the user's global role: any user can be given a stage duty.
    """

    class StageRoles(models.TextChoices):
        SPEAKER = "speaker", "Speaker"
        JUDGE = "judge", "Judge"
        COACH = "coach", "Coach"
        INSTRUCTOR = "instructor", "Instructor"
        MODERATOR = "moderator", "Moderator"
        OTHER = "other", "Other"

    stage = models.ForeignKey(Stage, on_delete=models.CASCADE, related_name="stage_roles")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="stage_roles",
    )
    role = models.CharField(max_length=20, choices=StageRoles.choices)

    class Meta:
        ordering = ["stage__order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["stage", "user"],
                name="unique_stage_user",
            ),
        ]

    def __str__(self):
        return f"{self.user.username} as {self.role} on {self.stage.title}"


class Attribute(models.Model):
    """
    Global catalog entry of the EAV system ("attribute" = the E).

    No JSONField anywhere: dynamic per-event data uses a typed EAV design
    (Attribute -> AttributeOption -> EventAttributeValue) so every value is
    stored in a typed column and can be indexed/constrained by the database.
    """

    class DataType(models.TextChoices):
        TEXT = "text", "Text"
        INTEGER = "integer", "Integer"
        DECIMAL = "decimal", "Decimal"
        BOOLEAN = "boolean", "Boolean"
        DATE = "date", "Date"
        CHOICE = "choice", "Choice"

    name = models.CharField(max_length=200)
    key = models.SlugField(max_length=200, unique=True, help_text="Unique machine key.")
    data_type = models.CharField(max_length=20, choices=DataType.choices)
    required = models.BooleanField(
        default=False,
        help_text="When set, a value must always be supplied for this attribute.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.data_type})"


class AttributeOption(models.Model):
    """Allowed values for attributes with data_type = choice ("option" = the V catalogue)."""

    attribute = models.ForeignKey(Attribute, on_delete=models.CASCADE, related_name="options")
    value = models.CharField(max_length=200)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["attribute", "value"],
                name="unique_option_value_per_attribute",
            ),
        ]

    def __str__(self):
        return f"{self.attribute.key}: {self.value}"


class EventAttributeValue(models.Model):
    """
    A single typed EAV value bound to an event ("value" = the V instance).

    Exactly one of the value_* columns carries the payload depending on the
    attribute's data_type; AttributeService guarantees the mapping and that
    (event, attribute) stays unique.
    """

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="attribute_values")
    attribute = models.ForeignKey(Attribute, on_delete=models.CASCADE, related_name="event_values")

    value_text = models.TextField(null=True, blank=True)
    value_integer = models.BigIntegerField(null=True, blank=True)
    value_decimal = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True
    )
    value_boolean = models.BooleanField(null=True, blank=True)
    value_date = models.DateField(null=True, blank=True)
    value_option = models.ForeignKey(
        AttributeOption,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="event_values",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["attribute__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "attribute"],
                name="unique_event_attribute",
            ),
        ]

    def __str__(self):
        return f"{self.event.title} / {self.attribute.key}"
