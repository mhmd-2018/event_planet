"""
Full happy-path walkthrough of the platform, exercising every API group in
the order a real organizer/participant would.
"""

from events.models import EventAttributeValue
from registrations.models import Registration, Feedback
from results.models import Result

from .base import BaseAPITestCase


class FullLifecycleTests(BaseAPITestCase):

    def test_organizer_to_public_results_flow(self):
        organizer = self.create_user("org", role="organizer")
        alice = self.create_user("alice")
        bob = self.create_user("bob")
        stranger = self.create_user("stranger")

        # ------------------------------------------------------------------
        # 1. Organizer creates a draft event.
        self.authenticate(organizer)
        response = self.client.post(
            "/api/v1/organizer/events/",
            {
                "title": "Galactic Hackathon",
                "description": "Build for Mars.",
                "start_at": self._iso(days=7),
                "end_at": self._iso(days=9),
                "capacity": 10,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        event_id = response.data["id"]
        self.assertEqual(response.data["status"], "draft")

        stages_url = f"/api/v1/organizer/events/{event_id}/stages/"
        status_url = f"/api/v1/organizer/events/{event_id}/status/"

        # ------------------------------------------------------------------
        # 2. Stages and a stage role are prepared while still a draft.
        response = self.client.post(
            stages_url,
            {
                "order": 1,
                "title": "Opening ceremony",
                "start_at": self._iso(days=7),
                "end_at": self._iso(days=7, hours=2),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        stage_id = response.data["id"]

        # Stage role: any user can be given a stage duty (independent of their
        # global role) — here a participant acts as judge.
        judge = self.create_user("jury")
        response = self.client.post(
            f"/api/v1/organizer/events/{event_id}/stages/{stage_id}/roles/",
            {"user": judge.id, "role": "judge"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["user_username"], "jury")

        # ------------------------------------------------------------------
        # 3. Publish -> event becomes publicly visible.
        response = self.client.post(status_url, {"status": "published"}, format="json")
        self.assertEqual(response.status_code, 200)

        public_response = self.client.get("/api/v1/public/events/")
        self.assertEqual([row["id"] for row in public_response.data["results"]], [event_id])

        # ------------------------------------------------------------------
        # 4. Participants register (capacity counting is event level).
        for user in (alice, bob):
            self.authenticate(user)
            response = self.client.post(
                f"/api/v1/participant/events/{event_id}/register/", format="json"
            )
            self.assertEqual(response.status_code, 201)
        self.assertEqual(Registration.objects.filter(event_id=event_id).count(), 2)

        # Organizer sees the participant list.
        self.authenticate(organizer)
        response = self.client.get(f"/api/v1/organizer/events/{event_id}/participants/")
        self.assertEqual(len(response.data), 2)

        # ------------------------------------------------------------------
        # 5. EAV: create a choice attribute and bind a typed value.
        response = self.client.post(
            "/api/v1/organizer/attributes/",
            {
                "name": "Format",
                "data_type": "choice",
                "options": [
                    {"value": "Onsite", "order": 0},
                    {"value": "Online", "order": 1},
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        attribute_id = response.data["id"]

        response = self.client.post(
            f"/api/v1/organizer/events/{event_id}/attribute-values/",
            {"attribute": attribute_id, "value": "Onsite"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)

        detail = self.client.get(f"/api/v1/public/events/{event_id}/")
        self.assertEqual(detail.data["attribute_values"][0]["value"], "Onsite")

        # ------------------------------------------------------------------
        # 6. Close -> registration no longer possible, event still public.
        self.client.post(status_url, {"status": "closed"}, format="json")
        self.authenticate(stranger)
        response = self.client.post(
            f"/api/v1/participant/events/{event_id}/register/", format="json"
        )
        self.assertEqual(response.status_code, 400)

        # ------------------------------------------------------------------
        # 7. Finish -> feedback (registered only) and results become possible.
        self.authenticate(organizer)
        self.client.post(status_url, {"status": "finished"}, format="json")

        # Alice (registered) submits feedback; stranger (not registered) cannot.
        self.authenticate(alice)
        self.assertEqual(
            self.client.post(
                f"/api/v1/participant/events/{event_id}/feedback/",
                {"rating": 5, "text": "Epic!"},
                format="json",
            ).status_code,
            201,
        )
        self.authenticate(stranger)
        self.assertEqual(
            self.client.post(
                f"/api/v1/participant/events/{event_id}/feedback/",
                {"rating": 1},
                format="json",
            ).status_code,
            403,
        )

        # ------------------------------------------------------------------
        # 8. Results: draft -> publish-all -> publicly visible.
        self.authenticate(organizer)
        results_url = f"/api/v1/organizer/events/{event_id}/results/"
        self.assertEqual(
            self.client.post(
                results_url,
                {"participant": alice.id, "rank": 1, "score": "98.5", "notes": "Perfect score"},
                format="json",
            ).status_code,
            201,
        )
        self.assertEqual(
            self.client.post(results_url, {"team_name": "Team Nebula", "rank": 2}, format="json").status_code,
            201,
        )

        # Publishing works because the event is finished.
        response = self.client.post(f"{results_url}publish-all/", format="json")
        self.assertEqual(response.data["published"], 2)

        self.logout()
        response = self.client.get(f"/api/v1/public/events/{event_id}/results/")
        rows = response.data["results"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["participant_username"], "alice")
        self.assertEqual(float(rows[0]["score"]), 98.5)
        self.assertEqual(rows[1]["team_name"], "Team Nebula")

        # Sanity: DB state matches expectations.
        self.assertEqual(EventAttributeValue.objects.filter(event_id=event_id).count(), 1)
        self.assertEqual(Feedback.objects.filter(event_id=event_id).count(), 1)
        self.assertEqual(Result.objects.filter(event_id=event_id, publish_at__isnull=True).count(), 0)

    @staticmethod
    def _iso(days, hours=0):
        from datetime import timedelta

        from django.utils import timezone

        return (timezone.now() + timedelta(days=days, hours=hours)).isoformat()
