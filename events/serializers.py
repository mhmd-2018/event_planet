from django.utils.text import slugify
from rest_framework import serializers

from .models import Attribute, AttributeOption, Event, EventAttributeValue, Stage, StageRole


# --------------------------------------------------------------------------- #
# EAV: Attribute catalog (defined first so events can embed values)
# --------------------------------------------------------------------------- #


class AttributeOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttributeOption
        fields = ["id", "value", "order"]


class AttributeMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attribute
        fields = ["id", "name", "key", "data_type", "required"]


class AttributeSerializer(serializers.ModelSerializer):
    options = AttributeOptionSerializer(many=True, required=False)
    key = serializers.SlugField(required=False, allow_blank=True, max_length=200)

    class Meta:
        model = Attribute
        fields = ["id", "name", "key", "data_type", "required", "options", "created_at"]
        read_only_fields = ["created_at"]

    def validate(self, attrs):
        data_type = attrs.get("data_type", getattr(self.instance, "data_type", None))
        options = attrs.get("options")

        if options and data_type != Attribute.DataType.CHOICE:
            raise serializers.ValidationError(
                {"options": "Options are only allowed for choice attributes."}
            )

        if data_type == Attribute.DataType.CHOICE:
            if options is not None and len(options) == 0:
                raise serializers.ValidationError(
                    {"options": "Choice attributes require at least one option."}
                )
            existing = self.instance.options.count() if self.instance else 0
            if options is None and existing == 0:
                raise serializers.ValidationError(
                    {"options": "Choice attributes require at least one option."}
                )

        if options:
            # Duplicate values inside one payload would violate the
            # unique (attribute, value) constraint at bulk_create time
            # and surface as an ugly HTTP 500 — reject them up front.
            values = [option["value"] for option in options]
            if len(values) != len(set(values)):
                raise serializers.ValidationError(
                    {"options": "Duplicate option values are not allowed."}
                )
        return attrs

    def _dedupe_key(self, name, key):
        base = slugify(key or name) or "attribute"
        candidate = base
        suffix = 2
        exclude_pk = self.instance.pk if self.instance else None
        while Attribute.objects.filter(key=candidate).exclude(pk=exclude_pk).exists():
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    def create(self, validated_data):
        options = validated_data.pop("options", [])
        explicit_key = validated_data.pop("key", "")
        if explicit_key:
            # An explicitly requested key must be free — no silent rename.
            if Attribute.objects.filter(key=explicit_key).exists():
                raise serializers.ValidationError({"key": "This key is already in use."})
            validated_data["key"] = explicit_key
        else:
            validated_data["key"] = self._dedupe_key(validated_data["name"], "")
        attribute = Attribute.objects.create(**validated_data)
        if attribute.data_type == Attribute.DataType.CHOICE and options:
            AttributeOption.objects.bulk_create(
                [AttributeOption(attribute=attribute, **option) for option in options]
            )
        return attribute

    def update(self, instance, validated_data):
        options = validated_data.pop("options", None)

        new_data_type = validated_data.get("data_type")
        if new_data_type and new_data_type != instance.data_type:
            # Changing the data type would orphan the already-stored typed
            # values (reads are routed by data_type), so block it while any
            # event value references this attribute.
            if EventAttributeValue.objects.filter(attribute=instance).exists():
                raise serializers.ValidationError(
                    {
                        "data_type": (
                            "Cannot change the data type while event values "
                            "reference this attribute; delete those values first."
                        )
                    }
                )
            if new_data_type != Attribute.DataType.CHOICE:
                # Safe: no bound values (guard above), so nothing cascades.
                instance.options.all().delete()

        if "key" in validated_data:
            new_key = validated_data.pop("key") or slugify(
                validated_data.get("name", instance.name)
            )
            if Attribute.objects.filter(key=new_key).exclude(pk=instance.pk).exists():
                raise serializers.ValidationError({"key": "This key is already in use."})
            validated_data["key"] = new_key

        if options is not None:
            # Replacing options must never silently destroy event data: the
            # old implementation deleted every option row, and the CASCADE
            # on EventAttributeValue.value_option wiped the bound values.
            new_values = {option["value"] for option in options}
            referenced = set(
                EventAttributeValue.objects.filter(
                    attribute=instance, value_option__isnull=False
                ).values_list("value_option__value", flat=True)
            )
            orphaned = referenced - new_values
            if orphaned:
                raise serializers.ValidationError(
                    {
                        "options": (
                            f"Cannot remove option(s) {sorted(orphaned)} while event "
                            "values still reference them; delete those event values first."
                        )
                    }
                )

        instance = super().update(instance, validated_data)

        if options is not None:
            # Reuse rows whose value survives so existing event values keep
            # pointing at them; drop only the truly unused ones, then add
            # anything new.
            existing_by_value = {option.value: option for option in instance.options.all()}
            instance.options.exclude(value__in=new_values).delete()
            for option_data in options:
                existing = existing_by_value.get(option_data["value"])
                if existing is None:
                    AttributeOption.objects.create(attribute=instance, **option_data)
                elif existing.order != option_data.get("order", existing.order):
                    existing.order = option_data.get("order", existing.order)
                    existing.save(update_fields=["order"])
        return instance


class EventAttributeValueReadSerializer(serializers.ModelSerializer):
    attribute = AttributeMiniSerializer(read_only=True)
    value = serializers.SerializerMethodField()

    class Meta:
        model = EventAttributeValue
        fields = ["id", "attribute", "value", "created_at", "updated_at"]

    def get_value(self, obj):
        data_type = obj.attribute.data_type
        if data_type == Attribute.DataType.CHOICE:
            return obj.value_option.value if obj.value_option_id else None
        if data_type == Attribute.DataType.TEXT:
            return obj.value_text
        if data_type == Attribute.DataType.INTEGER:
            return obj.value_integer
        if data_type == Attribute.DataType.DECIMAL:
            return obj.value_decimal
        if data_type == Attribute.DataType.BOOLEAN:
            return obj.value_boolean
        if data_type == Attribute.DataType.DATE:
            return obj.value_date
        return None


class EventAttributeValueInputSerializer(serializers.Serializer):
    attribute = serializers.PrimaryKeyRelatedField(queryset=Attribute.objects.all())
    value = serializers.JSONField(
        help_text="Typed scalar; must match the attribute data_type (validated by AttributeService)."
    )


# --------------------------------------------------------------------------- #
# Stages & stage roles
# --------------------------------------------------------------------------- #


class StageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stage
        fields = ["id", "order", "title", "description", "start_at", "end_at"]

    def validate(self, attrs):
        start = attrs.get("start_at", getattr(self.instance, "start_at", None))
        end = attrs.get("end_at", getattr(self.instance, "end_at", None))
        if start is not None and end is not None and end <= start:
            raise serializers.ValidationError({"end_at": "end_at must be after start_at."})
        return attrs


class StageRoleSerializer(serializers.ModelSerializer):
    user_username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = StageRole
        fields = ["id", "user", "user_username", "role"]


# --------------------------------------------------------------------------- #
# Events
# --------------------------------------------------------------------------- #


class EventBriefSerializer(serializers.ModelSerializer):
    """Minimal event representation embedded in other resources."""

    class Meta:
        model = Event
        fields = ["id", "title", "status", "start_at", "end_at"]


class EventWriteSerializer(serializers.ModelSerializer):
    """Create/update payload. NOTE: `status` is intentionally NOT writable —
    status changes must go through EventService via POST /events/{id}/status/."""

    class Meta:
        model = Event
        fields = ["title", "description", "start_at", "end_at", "capacity"]

    def validate(self, attrs):
        start = attrs.get("start_at", getattr(self.instance, "start_at", None))
        end = attrs.get("end_at", getattr(self.instance, "end_at", None))
        if start is not None and end is not None and end <= start:
            raise serializers.ValidationError({"end_at": "end_at must be after start_at."})
        return attrs


class EventStatusInputSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Event.Status.choices)


class EventReadSerializer(serializers.ModelSerializer):
    """Full organizer-facing representation."""

    owner_username = serializers.CharField(source="owner.username", read_only=True)
    registrations_count = serializers.IntegerField(
        source="active_registrations_count", read_only=True
    )
    spots_left = serializers.IntegerField(read_only=True)
    allowed_next_statuses = serializers.SerializerMethodField()
    stages = StageSerializer(many=True, read_only=True)
    attribute_values = EventAttributeValueReadSerializer(many=True, read_only=True)

    class Meta:
        model = Event
        fields = [
            "id",
            "title",
            "description",
            "start_at",
            "end_at",
            "capacity",
            "status",
            "owner",
            "owner_username",
            "registrations_count",
            "spots_left",
            "allowed_next_statuses",
            "stages",
            "attribute_values",
            "created_at",
            "updated_at",
        ]

    def get_allowed_next_statuses(self, obj):
        return obj.allowed_next_statuses()


# --------------------------------------------------------------------------- #
# Public representations
# --------------------------------------------------------------------------- #


class PublicEventListSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True)
    registered_count = serializers.IntegerField(
        source="active_registrations_count", read_only=True
    )
    spots_left = serializers.IntegerField(read_only=True)

    class Meta:
        model = Event
        fields = [
            "id",
            "title",
            "description",
            "start_at",
            "end_at",
            "capacity",
            "status",
            "owner_username",
            "registered_count",
            "spots_left",
        ]


class PublicEventDetailSerializer(PublicEventListSerializer):
    stages = StageSerializer(many=True, read_only=True)
    attribute_values = EventAttributeValueReadSerializer(many=True, read_only=True)

    class Meta(PublicEventListSerializer.Meta):
        fields = PublicEventListSerializer.Meta.fields + ["stages", "attribute_values"]
