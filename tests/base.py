from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

User = get_user_model()

PASSWORD = "Str0ngPass!23"


def event_payload(**overrides):
    payload = {
        "title": "Planet Hack 2026",
        "description": "A 48h hackathon across the galaxy.",
        "start_at": (timezone.now() + timedelta(days=7)).isoformat(),
        "end_at": (timezone.now() + timedelta(days=9)).isoformat(),
        "capacity": 50,
    }
    payload.update(overrides)
    return payload


class BaseAPITestCase(APITestCase):

    def create_user(self, username, role="participant", password=PASSWORD, **extra):
        return User.objects.create_user(
            username=username, password=password, role=role, **extra
        )

    def authenticate(self, user, password=PASSWORD):
        response = self.client.post(
            "/api/v1/auth/token/",
            {"username": user.username, "password": password},
            format="json",
        )
        self.assertEqual(response.status_code, 200, getattr(response, "data", response.content))
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        return response.data

    def logout(self):
        self.client.credentials()

    def make_event(self, owner, status="draft", capacity=50, **overrides):
        from events.models import Event

        payload = event_payload()
        payload.update(overrides)
        payload["capacity"] = capacity
        return Event.objects.create(owner=owner, status=status, **payload)

    def advance(self, event, *statuses, owner=None):
        """Drive an event through the lifecycle via the service (as owner)."""
        from events.services import EventService

        owner = owner or event.owner
        for new_status in statuses:
            EventService.change_status(event, owner, new_status)
            event.refresh_from_db()
        return event
