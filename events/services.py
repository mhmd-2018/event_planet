"""
Service layer for events.

Core decision: **status changes and all event mutations happen here, never
directly through serializers/API payloads.** Views stay thin: validate input,
delegate to a service, render the result.
"""

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from .models import Attribute, Event, EventAttributeValue

MAX_BIGINT = 2**63 - 1
# Match the EventAttributeValue.value_decimal column limits so out-of-range
# input becomes a clean 400 instead of a database error (HTTP 500).
MAX_DECIMAL_DIGITS = 14
MAX_DECIMAL_PLACES = 4


class EventService:
    """Creation, editing and the Draft -> Published -> Closed -> Finished machine."""

    @staticmethod
    def create_event(owner, validated_data: dict) -> Event:
        return Event.objects.create(owner=owner, **validated_data)

    @staticmethod
    def update_event(event: Event, user, validated_data: dict) -> Event:
        if event.owner_id != user.id:
            raise PermissionDenied("Only the event owner can edit this event.")
        for field, value in validated_data.items():
            setattr(event, field, value)
        event.save()
        return event

    @staticmethod
    def change_status(event: Event, user, new_status: str) -> Event:
        """Enforce ownership + the strictly forward transition matrix."""
        if event.owner_id != user.id:
            raise PermissionDenied("Only the event owner can change the event status.")
        if new_status not in Event.Status.values:
            raise ValidationError({"status": f"Unknown status '{new_status}'."})

        allowed = Event.TRANSITIONS[event.status]
        if new_status not in allowed:
            allowed_names = [s.value for s in allowed] or ["<none>"]
            raise ValidationError(
                {
                    "status": (
                        f"Illegal transition '{event.status}' -> '{new_status}'. "
                        f"Allowed next statuses: {allowed_names}."
                    )
                }
            )

        event.status = new_status
        event.save(update_fields=["status", "updated_at"])
        return event


class AttributeService:
    """
    EAV validation & persistence.

    Validates an incoming dynamic value against the attribute's data_type and
    maps it onto exactly one typed column of EventAttributeValue. Using typed
    columns (instead of JSONField) keeps values queryable and lets the DB
    enforce integrity.
    """

    VALUE_COLUMNS = {
        Attribute.DataType.TEXT: "value_text",
        Attribute.DataType.INTEGER: "value_integer",
        Attribute.DataType.DECIMAL: "value_decimal",
        Attribute.DataType.BOOLEAN: "value_boolean",
        Attribute.DataType.DATE: "value_date",
        Attribute.DataType.CHOICE: "value_option",
    }

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #

    @classmethod
    def validate_value(cls, attribute: Attribute, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValidationError(
                {
                    "value": (
                        "A value is required."
                        if attribute.required
                        else "Empty values are not allowed; use DELETE to remove the value."
                    )
                }
            )
        parsers = {
            Attribute.DataType.TEXT: cls._parse_text,
            Attribute.DataType.INTEGER: cls._parse_integer,
            Attribute.DataType.DECIMAL: cls._parse_decimal,
            Attribute.DataType.BOOLEAN: cls._parse_boolean,
            Attribute.DataType.DATE: cls._parse_date,
            Attribute.DataType.CHOICE: cls._parse_choice,
        }
        return parsers[attribute.data_type](attribute, value)

    @staticmethod
    def _parse_text(attribute, value):
        if not isinstance(value, str):
            raise ValidationError({"value": "Expected a text value."})
        return {"value_text": value}

    @staticmethod
    def _parse_integer(attribute, value):
        if isinstance(value, bool):
            raise ValidationError({"value": "Expected an integer value."})
        if isinstance(value, int):
            number = value
        elif isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip()):
            number = int(value.strip())
        else:
            raise ValidationError({"value": "Expected an integer value."})
        if abs(number) > MAX_BIGINT:
            raise ValidationError({"value": "Integer value out of range."})
        return {"value_integer": number}

    @staticmethod
    def _parse_decimal(attribute, value):
        if isinstance(value, bool):
            raise ValidationError({"value": "Expected a decimal value."})
        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise ValidationError({"value": "Expected a decimal value."})
        if not number.is_finite():
            raise ValidationError({"value": "Decimal value must be finite."})
        # Enforce the same limits as the value_decimal column
        # (max_digits=14, decimal_places=4) before the database sees it.
        _sign, digits, exponent = number.as_tuple()
        decimal_places = max(-exponent, 0)
        integer_digits = max(len(digits) + exponent, 0)
        if (
            decimal_places > MAX_DECIMAL_PLACES
            or integer_digits + decimal_places > MAX_DECIMAL_DIGITS
        ):
            raise ValidationError(
                {
                    "value": (
                        f"Decimal value out of range: at most {MAX_DECIMAL_DIGITS} digits "
                        f"in total and no more than {MAX_DECIMAL_PLACES} decimal places."
                    )
                }
            )
        return {"value_decimal": number}

    @staticmethod
    def _parse_boolean(attribute, value):
        if isinstance(value, bool):
            return {"value_boolean": value}
        if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
            return {"value_boolean": value.strip().lower() == "true"}
        if isinstance(value, int) and value in (0, 1):
            return {"value_boolean": bool(value)}
        raise ValidationError({"value": "Expected a boolean value (true/false)."})

    @staticmethod
    def _parse_date(attribute, value):
        if isinstance(value, str):
            try:
                return {"value_date": date.fromisoformat(value.strip())}
            except ValueError:
                raise ValidationError({"value": "Expected an ISO date (YYYY-MM-DD)."})
        raise ValidationError({"value": "Expected an ISO date (YYYY-MM-DD)."})

    @staticmethod
    def _parse_choice(attribute, value):
        if not isinstance(value, str):
            raise ValidationError({"value": "Expected the value of one of the attribute options."})
        option = attribute.options.filter(value=value).first()
        if option is None:
            allowed = list(attribute.options.values_list("value", flat=True))
            raise ValidationError(
                {"value": f"Invalid option '{value}'. Allowed options: {allowed}."}
            )
        return {"value_option": option}

    # ------------------------------------------------------------------ #
    # Persistence (upsert on the unique (event, attribute) pair)
    # ------------------------------------------------------------------ #

    @classmethod
    def upsert_event_value(cls, event, attribute: Attribute, value):
        payload = cls.validate_value(attribute, value)
        # Reset every column so switching the payload column never leaves
        # stale data behind, then apply the validated value.
        defaults = {column: None for column in cls.VALUE_COLUMNS.values()}
        defaults.update(payload)
        instance, created = EventAttributeValue.objects.update_or_create(
            event=event,
            attribute=attribute,
            defaults=defaults,
        )
        return instance, created

    @staticmethod
    def get_event_or_404(event_id, owner=None):
        queryset = Event.objects.all()
        if owner is not None:
            queryset = queryset.filter(owner=owner)
        event = queryset.filter(pk=event_id).first()
        if event is None:
            raise NotFound("Event not found.")
        return event
