from django.db import IntegrityError, transaction
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404
from rest_framework import status as http_status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.generics import (
    ListCreateAPIView,
    RetrieveDestroyAPIView,
    RetrieveUpdateDestroyAPIView,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from common.permissions import IsOrganizer
from registrations.serializers import FeedbackSerializer, RegistrationSerializer

from .models import Attribute, Event, EventAttributeValue, Stage, StageRole
from .serializers import (
    AttributeSerializer,
    EventAttributeValueInputSerializer,
    EventAttributeValueReadSerializer,
    EventReadSerializer,
    EventStatusInputSerializer,
    EventWriteSerializer,
    PublicEventDetailSerializer,
    PublicEventListSerializer,
    StageRoleSerializer,
    StageSerializer,
)
from .services import AttributeService, EventService


# --------------------------------------------------------------------------- #
# Public API (no authentication)
# --------------------------------------------------------------------------- #


class PublicEventViewSet(ReadOnlyModelViewSet):
    """
    Public, read-only exposure of events.

    Core decision: only events that are published at some point are visible
    (status in published/closed/finished). Drafts never leak.
    """

    permission_classes = [AllowAny]
    search_fields = ["title", "description"]
    ordering_fields = ["start_at", "end_at", "title", "created_at"]
    ordering = ["-start_at"]

    def get_queryset(self):
        return (
            Event.objects.filter(status__in=Event.PUBLIC_STATUSES)
            # Annotated so the list endpoints don't run one COUNT(*) per row
            # (Event.active_registrations_count prefers the annotation).
            .annotate(
                _active_registrations_count=Count(
                    "registrations", filter=Q(registrations__status="active")
                )
            )
            .select_related("owner")
            .prefetch_related(
                "stages",
                Prefetch(
                    "attribute_values",
                    queryset=EventAttributeValue.objects.select_related("attribute"),
                ),
            )
        )

    def get_serializer_class(self):
        if self.action == "retrieve":
            return PublicEventDetailSerializer
        return PublicEventListSerializer


# --------------------------------------------------------------------------- #
# Organizer API — events
# --------------------------------------------------------------------------- #


class OrganizerEventViewSet(ModelViewSet):
    """CRUD over the organizer's OWN events + status machine + participant list."""

    permission_classes = [IsOrganizer]

    def get_queryset(self):
        return (
            Event.objects.filter(owner=self.request.user)
            # Same N+1 avoidance as the public list (see above).
            .annotate(
                _active_registrations_count=Count(
                    "registrations", filter=Q(registrations__status="active")
                )
            )
            .select_related("owner")
            .prefetch_related(
                "stages",
                Prefetch(
                    "attribute_values",
                    queryset=EventAttributeValue.objects.select_related("attribute"),
                ),
            )
        )

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return EventWriteSerializer
        return EventReadSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event = EventService.create_event(request.user, serializer.validated_data)
        output = EventReadSerializer(event, context=self.get_serializer_context())
        return Response(output.data, status=http_status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        EventService.update_event(instance, request.user, serializer.validated_data)
        output = EventReadSerializer(instance, context=self.get_serializer_context())
        return Response(output.data)

    @action(detail=True, methods=["post"], url_path="status")
    def change_status(self, request, pk=None):
        """The ONLY way to move an event through its lifecycle (service layer)."""
        event = self.get_object()
        input_serializer = EventStatusInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        event = EventService.change_status(
            event, request.user, input_serializer.validated_data["status"]
        )
        output = EventReadSerializer(event, context=self.get_serializer_context())
        return Response(output.data)

    @action(detail=True, methods=["get"], url_path="participants")
    def participants(self, request, pk=None):
        """List registrations for the event (owner only)."""
        event = self.get_object()
        registrations = event.registrations.select_related("participant", "event").order_by(
            "-registered_at"
        )
        return Response(RegistrationSerializer(registrations, many=True).data)

    @action(detail=True, methods=["get"], url_path="feedback")
    def feedback(self, request, pk=None):
        """List feedback submitted for the event (owner only)."""
        event = self.get_object()
        feedbacks = event.feedback.select_related("participant", "event").order_by(
            "-created_at"
        )
        return Response(FeedbackSerializer(feedbacks, many=True).data)


# --------------------------------------------------------------------------- #
# Organizer API — stages & stage roles
# --------------------------------------------------------------------------- #


class OrganizerStageListCreateView(ListCreateAPIView):
    serializer_class = StageSerializer
    permission_classes = [IsOrganizer]

    def get_queryset(self):
        return Stage.objects.filter(
            event_id=self.kwargs["event_pk"], event__owner=self.request.user
        ).select_related("event")

    def perform_create(self, serializer):
        event = get_object_or_404(
            Event, pk=self.kwargs["event_pk"], owner=self.request.user
        )
        try:
            # Nested atomic: an IntegrityError only rolls back the savepoint,
            # keeping the surrounding transaction usable.
            with transaction.atomic():
                serializer.save(event=event)
        except IntegrityError:
            raise ValidationError(
                {"order": "A stage with this order already exists for the event."}
            )


class OrganizerStageDetailView(RetrieveUpdateDestroyAPIView):
    serializer_class = StageSerializer
    permission_classes = [IsOrganizer]

    def get_queryset(self):
        return Stage.objects.filter(
            event_id=self.kwargs["event_pk"], event__owner=self.request.user
        )

    def perform_update(self, serializer):
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError:
            raise ValidationError(
                {"order": "A stage with this order already exists for the event."}
            )


class OrganizerStageRoleListCreateView(ListCreateAPIView):
    serializer_class = StageRoleSerializer
    permission_classes = [IsOrganizer]

    def get_queryset(self):
        return StageRole.objects.filter(
            stage_id=self.kwargs["stage_pk"],
            stage__event_id=self.kwargs["event_pk"],
            stage__event__owner=self.request.user,
        ).select_related("user", "stage")

    def perform_create(self, serializer):
        stage = get_object_or_404(
            Stage,
            pk=self.kwargs["stage_pk"],
            event_id=self.kwargs["event_pk"],
            event__owner=self.request.user,
        )
        try:
            with transaction.atomic():
                serializer.save(stage=stage)
        except IntegrityError:
            raise ValidationError(
                {"user": "This user already has a role on this stage."}
            )


class OrganizerStageRoleDetailView(RetrieveDestroyAPIView):
    serializer_class = StageRoleSerializer
    permission_classes = [IsOrganizer]

    def get_queryset(self):
        return StageRole.objects.filter(
            stage_id=self.kwargs["stage_pk"],
            stage__event_id=self.kwargs["event_pk"],
            stage__event__owner=self.request.user,
        )


# --------------------------------------------------------------------------- #
# Organizer API — attribute catalog & per-event EAV values
# --------------------------------------------------------------------------- #


class AttributeViewSet(ModelViewSet):
    """
    Global attribute catalog (shared across organizers — documented core
    decision). Creating/modifying the catalog is allowed for any organizer;
    binding values to an event requires event ownership.
    """

    serializer_class = AttributeSerializer
    permission_classes = [IsOrganizer]
    queryset = Attribute.objects.all().prefetch_related("options")


class OrganizerEventAttributeValueListCreateView(ListCreateAPIView):
    """GET lists values; POST upserts a typed value for (event, attribute)."""

    permission_classes = [IsOrganizer]

    def get_queryset(self):
        return EventAttributeValue.objects.filter(
            event_id=self.kwargs["event_pk"], event__owner=self.request.user
        ).select_related("attribute")

    def get_serializer_class(self):
        return EventAttributeValueReadSerializer

    def post(self, request, *args, **kwargs):
        event = get_object_or_404(
            Event, pk=self.kwargs["event_pk"], owner=request.user
        )
        input_serializer = EventAttributeValueInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        instance, created = AttributeService.upsert_event_value(
            event,
            input_serializer.validated_data["attribute"],
            input_serializer.validated_data["value"],
        )
        output = EventAttributeValueReadSerializer(instance)
        return Response(
            output.data,
            status=http_status.HTTP_201_CREATED if created else http_status.HTTP_200_OK,
        )


class OrganizerEventAttributeValueDetailView(RetrieveDestroyAPIView):
    serializer_class = EventAttributeValueReadSerializer
    permission_classes = [IsOrganizer]

    def get_queryset(self):
        return EventAttributeValue.objects.filter(
            event_id=self.kwargs["event_pk"], event__owner=self.request.user
        ).select_related("attribute")
