from rest_framework import serializers

from events.serializers import EventBriefSerializer

from .models import Feedback, Registration


class RegistrationSerializer(serializers.ModelSerializer):
    event = EventBriefSerializer(read_only=True)
    participant_username = serializers.CharField(source="participant.username", read_only=True)

    class Meta:
        model = Registration
        fields = [
            "id",
            "event",
            "participant",
            "participant_username",
            "status",
            "registered_at",
            "cancelled_at",
        ]


class FeedbackSerializer(serializers.ModelSerializer):
    event = EventBriefSerializer(read_only=True)
    participant_username = serializers.CharField(source="participant.username", read_only=True)

    class Meta:
        model = Feedback
        fields = [
            "id",
            "event",
            "participant",
            "participant_username",
            "rating",
            "text",
            "created_at",
            "updated_at",
        ]


class FeedbackInputSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    text = serializers.CharField(required=False, allow_blank=True, max_length=5000)
