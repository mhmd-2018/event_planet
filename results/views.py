from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status as http_status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from common.permissions import IsOrganizer
from events.models import Event

from .models import Result
from .serializers import (
    PublicResultSerializer,
    ResultPublishInputSerializer,
    ResultReadSerializer,
    ResultWriteSerializer,
)
from .services import ResultService


class OrganizerResultViewSet(ModelViewSet):
    """Draft CRUD + publish actions for the event owner."""

    permission_classes = [IsOrganizer]

    def get_queryset(self):
        return Result.objects.filter(
            event_id=self.kwargs["event_pk"], event__owner=self.request.user
        ).select_related("participant", "event")

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return ResultWriteSerializer
        return ResultReadSerializer

    def _save_guard(self, serializer, event):
        try:
            with transaction.atomic():
                serializer.save(event=event)
        except IntegrityError:
            raise ValidationError(
                {"detail": "A result must target a participant or a team_name."}
            )

    def perform_create(self, serializer):
        event = get_object_or_404(
            Event, pk=self.kwargs["event_pk"], owner=self.request.user
        )
        self._save_guard(serializer, event)

    def perform_update(self, serializer):
        self._save_guard(serializer, serializer.instance.event)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        output = ResultReadSerializer(serializer.instance, context=self.get_serializer_context())
        return Response(output.data, status=http_status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="publish")
    def publish(self, request, event_pk=None, pk=None):
        result = self.get_object()
        input_serializer = ResultPublishInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        ResultService.publish(result, request.user, input_serializer.validated_data.get("publish_at"))
        return Response(ResultReadSerializer(result).data)

    @action(detail=False, methods=["post"], url_path="publish-all")
    def publish_all(self, request, event_pk=None):
        event = get_object_or_404(Event, pk=event_pk, owner=request.user)
        count = ResultService.publish_all(event, request.user)
        return Response({"published": count})


class PublicResultsView(ListAPIView):
    """GET /api/v1/public/events/{event_id}/results/ — published results only."""

    serializer_class = PublicResultSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        event = get_object_or_404(
            Event.objects.filter(status__in=Event.PUBLIC_STATUSES),
            pk=self.kwargs["event_id"],
        )
        return (
            Result.objects.filter(
                event=event,
                publish_at__isnull=False,
                publish_at__lte=timezone.now(),
            )
            .select_related("participant")
            .order_by("rank", "id")
        )
