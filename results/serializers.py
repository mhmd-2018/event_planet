from django.contrib.auth import get_user_model
from rest_framework import serializers

from events.serializers import EventBriefSerializer

from .models import Result

User = get_user_model()


class ResultWriteSerializer(serializers.ModelSerializer):
    """Create/update a result draft. `publish_at` is only set via publish actions."""

    participant = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_active=True), required=False, allow_null=True
    )
    team_name = serializers.CharField(required=False, allow_blank=True, max_length=200)
    rank = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    score = serializers.DecimalField(
        max_digits=12, decimal_places=4, required=False, allow_null=True
    )

    class Meta:
        model = Result
        fields = ["participant", "team_name", "rank", "score", "notes"]

    def validate(self, attrs):
        participant = attrs.get("participant", getattr(self.instance, "participant", None))
        team_name = attrs.get("team_name", getattr(self.instance, "team_name", ""))

        has_participant = participant is not None
        has_team = bool(team_name)

        if has_participant and has_team:
            raise serializers.ValidationError(
                {"detail": "Provide either a participant or a team_name, not both."}
            )
        if not has_participant and not has_team:
            raise serializers.ValidationError(
                {"detail": "A result must target a participant or a team_name."}
            )
        return attrs


class ResultReadSerializer(serializers.ModelSerializer):
    event = EventBriefSerializer(read_only=True)
    participant_username = serializers.CharField(
        source="participant.username", read_only=True, default=None
    )
    score = serializers.DecimalField(
        max_digits=12, decimal_places=4, coerce_to_string=False, read_only=True
    )

    class Meta:
        model = Result
        fields = [
            "id",
            "event",
            "participant",
            "participant_username",
            "team_name",
            "rank",
            "score",
            "notes",
            "publish_at",
            "created_at",
            "updated_at",
        ]


class ResultPublishInputSerializer(serializers.Serializer):
    publish_at = serializers.DateTimeField(
        required=False,
        help_text="Optional ISO 8601 datetime; defaults to now (scheduling supported).",
    )


class PublicResultSerializer(serializers.ModelSerializer):
    participant_username = serializers.CharField(
        source="participant.username", read_only=True, default=None
    )
    score = serializers.DecimalField(
        max_digits=12, decimal_places=4, coerce_to_string=False, read_only=True
    )

    class Meta:
        model = Result
        fields = ["id", "rank", "score", "notes", "participant", "participant_username", "team_name", "publish_at"]
