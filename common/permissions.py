"""
Reusable permission classes required by the project spec:
IsOrganizer, IsParticipant, IsEventOwner, IsRegisteredParticipant, IsEventFinished.

Defence-in-depth: permissions block requests at the HTTP boundary (401/403/404)
while the service layer re-checks the same business rules for any caller.
"""

from django.contrib.auth import get_user_model
from rest_framework.permissions import BasePermission
from rest_framework.exceptions import NotFound

from events.models import Event
from registrations.models import Registration

User = get_user_model()


def resolve_event(obj):
    """Best-effort resolution of the related Event for an arbitrary object."""
    if isinstance(obj, Event):
        return obj
    event = getattr(obj, "event", None)
    if event is not None:
        return event
    stage = getattr(obj, "stage", None)
    if stage is not None:
        return stage.event
    return None


class IsOrganizer(BasePermission):
    message = "Only organizers can perform this action."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.has_role(User.Roles.ORGANIZER))


class IsParticipant(BasePermission):
    message = "Only participants can perform this action."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.has_role(User.Roles.PARTICIPANT))


class IsEventOwner(BasePermission):
    """Object-level: the caller must own the event related to the object."""

    message = "You are not the owner of this event."

    def has_object_permission(self, request, view, obj):
        event = resolve_event(obj)
        if event is None:
            return False
        user = request.user
        return bool(user and user.is_authenticated and event.owner_id == user.id)


class IsRegisteredParticipant(BasePermission):
    """
    View-level: the URL must reference an event (event_id/event_pk) for which
    the caller holds an ACTIVE registration.
    """

    message = "You must be a registered participant of this event."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        event_id = view.kwargs.get("event_id") or view.kwargs.get("event_pk")
        if event_id is None:
            return False
        event = Event.objects.filter(pk=event_id).first()
        if event is None:
            raise NotFound("Event not found.")
        return Registration.objects.filter(
            event=event,
            participant=request.user,
            status=Registration.Status.ACTIVE,
        ).exists()


class IsEventFinished(BasePermission):
    """View-level: the event referenced by the URL must be FINISHED."""

    message = "This action is only available for finished events."

    def has_permission(self, request, view):
        event_id = view.kwargs.get("event_id") or view.kwargs.get("event_pk")
        if event_id is None:
            return False
        event = Event.objects.filter(pk=event_id).first()
        if event is None:
            raise NotFound("Event not found.")
        return event.status == Event.Status.FINISHED
