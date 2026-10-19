from django.shortcuts import get_object_or_404
from rest_framework import status as http_status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import IsEventFinished, IsParticipant, IsRegisteredParticipant

from .models import Feedback, Registration
from .serializers import (
    FeedbackInputSerializer,
    FeedbackSerializer,
    RegistrationSerializer,
)
from .services import FeedbackService, RegistrationService


class ParticipantRegisterView(APIView):
    """POST /api/v1/participant/events/{event_id}/register/"""

    permission_classes = [IsAuthenticated, IsParticipant]

    def post(self, request, event_id):
        registration, created = RegistrationService.register(request.user, event_id)
        return Response(
            RegistrationSerializer(registration).data,
            status=http_status.HTTP_201_CREATED if created else http_status.HTTP_200_OK,
        )


class MyRegistrationsView(ListAPIView):
    """GET /api/v1/participant/registrations/ — only the caller's own rows."""

    serializer_class = RegistrationSerializer
    permission_classes = [IsAuthenticated, IsParticipant]

    def get_queryset(self):
        return Registration.objects.filter(participant=self.request.user).select_related("event")


class CancelRegistrationView(APIView):
    """POST /api/v1/participant/registrations/{id}/cancel/"""

    permission_classes = [IsAuthenticated, IsParticipant]

    def post(self, request, pk):
        registration = get_object_or_404(
            Registration, pk=pk, participant=request.user
        )
        registration = RegistrationService.cancel(registration)
        return Response(RegistrationSerializer(registration).data)


class ParticipantFeedbackView(APIView):
    """POST /api/v1/participant/events/{event_id}/feedback/ (upsert)."""

    permission_classes = [
        IsAuthenticated,
        IsParticipant,
        IsRegisteredParticipant,
        IsEventFinished,
    ]

    def post(self, request, event_id):
        input_serializer = FeedbackInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        existed = Feedback.objects.filter(
            event_id=event_id, participant=request.user
        ).exists()
        feedback = FeedbackService.submit_feedback(
            request.user,
            event_id,
            rating=input_serializer.validated_data["rating"],
            text=input_serializer.validated_data.get("text", ""),
        )
        return Response(
            FeedbackSerializer(feedback).data,
            status=http_status.HTTP_200_OK if existed else http_status.HTTP_201_CREATED,
        )
