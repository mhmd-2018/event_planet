from datetime import timedelta
from unittest import skipUnless

import threading

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from events.models import Event
from registrations.models import Registration

from .base import PASSWORD, BaseAPITestCase

User = get_user_model()


class RegistrationAPITests(BaseAPITestCase):

    def setUp(self):
        self.organizer = self.create_user("organizer", role="organizer")
        self.event = self.make_event(self.organizer, status="published", capacity=2)
        self.alice = self.create_user("alice")
        self.bob = self.create_user("bob")
        self.carol = self.create_user("carol")

    def register(self, user, event=None):
        self.authenticate(user)
        return self.client.post(
            f"/api/v1/participant/events/{(event or self.event).id}/register/", format="json"
        )

    # ------------------------------------------------------------ success

    def test_register_success(self):
        response = self.register(self.alice)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], "active")
        self.assertEqual(response.data["participant_username"], "alice")
        self.assertEqual(Registration.objects.filter(event=self.event).count(), 1)

    def test_duplicate_registration_rejected(self):
        self.register(self.alice)
        response = self.register(self.alice)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Registration.objects.filter(event=self.event).count(), 1)

    # ------------------------------------------------------- event status

    def test_register_draft_event_rejected(self):
        draft = self.make_event(self.organizer, status="draft")
        response = self.register(self.alice, event=draft)
        self.assertEqual(response.status_code, 400)

    def test_register_closed_event_rejected(self):
        closed = self.make_event(self.organizer, status="closed")
        response = self.register(self.alice, event=closed)
        self.assertEqual(response.status_code, 400)

    def test_register_finished_event_rejected(self):
        finished = self.make_event(self.organizer, status="finished")
        response = self.register(self.alice, event=finished)
        self.assertEqual(response.status_code, 400)

    def test_register_unknown_event_404(self):
        self.authenticate(self.alice)
        response = self.client.post("/api/v1/participant/events/99999/register/", format="json")
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------ capacity

    def test_capacity_reached_rejected(self):
        self.assertEqual(self.register(self.alice).status_code, 201)
        self.assertEqual(self.register(self.bob).status_code, 201)
        response = self.register(self.carol)  # capacity is 2
        self.assertEqual(response.status_code, 400)
        self.assertIn("capacity", str(response.data).lower())

    def test_cancellation_frees_capacity(self):
        self.register(self.alice)
        self.register(self.bob)

        self.authenticate(self.alice)
        registration_id = Registration.objects.get(event=self.event, participant=self.alice).id
        response = self.client.post(f"/api/v1/participant/registrations/{registration_id}/cancel/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "cancelled")

        # Carol now fits into the freed slot.
        self.assertEqual(self.register(self.carol).status_code, 201)

    def test_reactivate_after_cancel(self):
        self.register(self.alice)
        registration_id = Registration.objects.get(event=self.event, participant=self.alice).id
        self.authenticate(self.alice)
        self.client.post(f"/api/v1/participant/registrations/{registration_id}/cancel/")
        response = self.client.post(
            f"/api/v1/participant/events/{self.event.id}/register/", format="json"
        )
        self.assertEqual(response.status_code, 200)  # re-activation, not a new row
        self.assertEqual(response.data["status"], "active")
        self.assertEqual(Registration.objects.filter(event=self.event).count(), 1)

    def test_cancel_twice_rejected(self):
        self.register(self.alice)
        registration_id = Registration.objects.get(event=self.event, participant=self.alice).id
        self.authenticate(self.alice)
        self.client.post(f"/api/v1/participant/registrations/{registration_id}/cancel/")
        response = self.client.post(f"/api/v1/participant/registrations/{registration_id}/cancel/")
        self.assertEqual(response.status_code, 400)

    def test_cannot_cancel_finished_event_registration(self):
        self.register(self.alice)
        self.advance(self.event, "closed", "finished")
        registration_id = Registration.objects.get(event=self.event, participant=self.alice).id
        self.authenticate(self.alice)
        response = self.client.post(f"/api/v1/participant/registrations/{registration_id}/cancel/")
        self.assertEqual(response.status_code, 400)

    # ---------------------------------------------------------- list / roles

    def test_my_registrations_only_own(self):
        self.register(self.alice)
        self.authenticate(self.bob)
        response = self.client.get("/api/v1/participant/registrations/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 0)

        self.authenticate(self.alice)
        response = self.client.get("/api/v1/participant/registrations/")
        self.assertEqual(len(response.data["results"]), 1)

    def test_organizer_cannot_register(self):
        response = self.register(self.organizer)
        self.assertEqual(response.status_code, 403)

    def test_anonymous_cannot_register(self):
        self.logout()
        response = self.client.post(
            f"/api/v1/participant/events/{self.event.id}/register/", format="json"
        )
        self.assertEqual(response.status_code, 401)


class RegistrationConcurrencyTests(TransactionTestCase):
    """
    Proof that event-level capacity is race-condition safe on PostgreSQL.

    Why this MUST be a TransactionTestCase and not APITestCase:
    * APITestCase wraps every test in an atomic block that is rolled back at
      the end — nothing is ever committed.
    * Each worker thread gets its OWN database connection (Django connections
      are thread-local), and on PostgreSQL a separate connection can only see
      COMMITTED rows.
    * The old version of this test lived inside APITestCase, so the event
      created in setUp was invisible to the workers and every worker received
      404 — it could never pass on PostgreSQL.

    The winner of the race is a brand-new registration, and a fresh
    registration returns HTTP 201 (HTTP 200 is only used for re-activation),
    so the expected outcome pair is {201, 400}.
    """

    @skipUnless(
        connection.vendor == "postgresql",
        "Row-level locking race test requires PostgreSQL (SQLite locks are no-ops).",
    )
    def test_concurrent_registrations_respect_capacity(self):
        """Two users race for the last slot of a capacity-1 event."""
        organizer = User.objects.create_user(
            username="race_organizer", password=PASSWORD, role="organizer"
        )
        solo = Event.objects.create(
            owner=organizer,
            title="Last Slot Sprint",
            start_at=timezone.now() + timedelta(days=1),
            end_at=timezone.now() + timedelta(days=2),
            capacity=1,
            status=Event.Status.PUBLISHED,
        )
        for username in ("racer_a", "racer_b"):
            User.objects.create_user(username=username, password=PASSWORD)

        outcomes = []

        def worker(username):
            client = APIClient()
            token_response = client.post(
                "/api/v1/auth/token/",
                {"username": username, "password": PASSWORD},
                format="json",
            )
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token_response.data['access']}")
            response = client.post(
                f"/api/v1/participant/events/{solo.id}/register/", format="json"
            )
            outcomes.append(response.status_code)
            connection.close()

        threads = [
            threading.Thread(target=worker, args=(username,))
            for username in ("racer_a", "racer_b")
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # One winner (201 = created) and one loser (400 = capacity reached).
        self.assertEqual(sorted(outcomes), [201, 400])
        self.assertEqual(
            Registration.objects.filter(event=solo, status="active").count(), 1
        )
