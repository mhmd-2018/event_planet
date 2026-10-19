"""
Cross-cutting role/permission checks (spec: "Permissions (owner, participant, public)").
"""

from .base import BaseAPITestCase, event_payload


class RoleBasedAccessTests(BaseAPITestCase):

    def setUp(self):
        self.organizer = self.create_user("organizer", role="organizer")
        self.participant = self.create_user("participant")
        self.event = self.make_event(self.organizer, status="published")

    # ------------------------------------------------------------- public

    def test_public_endpoints_open_to_anonymous(self):
        self.assertEqual(self.client.get("/api/v1/public/events/").status_code, 200)
        self.assertEqual(
            self.client.get(f"/api/v1/public/events/{self.event.id}/").status_code, 200
        )
        self.assertEqual(
            self.client.get(f"/api/v1/public/events/{self.event.id}/results/").status_code, 200
        )

    # --------------------------------------------------------- organizer API

    def test_organizer_api_requires_authentication(self):
        response = self.client.get("/api/v1/organizer/events/")
        self.assertEqual(response.status_code, 401)

    def test_organizer_api_requires_organizer_role(self):
        self.authenticate(self.participant)
        response = self.client.get("/api/v1/organizer/events/")
        self.assertEqual(response.status_code, 403)

    def test_participant_cannot_create_attribute(self):
        self.authenticate(self.participant)
        response = self.client.post(
            "/api/v1/organizer/attributes/",
            {"name": "Nope", "data_type": "text"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    # ------------------------------------------------------- participant API

    def test_participant_register_requires_participant_role(self):
        self.authenticate(self.organizer)
        response = self.client.post(
            f"/api/v1/participant/events/{self.event.id}/register/", format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_participant_api_requires_authentication(self):
        response = self.client.get("/api/v1/participant/registrations/")
        self.assertEqual(response.status_code, 401)

    # --------------------------------------------------------- owner checks

    def test_owner_queryset_isolation(self):
        other = self.create_user("other", role="organizer")
        foreign = self.make_event(other, status="published")

        self.authenticate(self.organizer)
        # Direct object access to a foreign event is 404 (queryset filtered).
        self.assertEqual(
            self.client.get(f"/api/v1/organizer/events/{foreign.id}/").status_code, 404
        )
        # Creating a stage for someone else's event is also hidden.
        response = self.client.post(
            f"/api/v1/organizer/events/{foreign.id}/stages/",
            {
                "order": 1,
                "title": "Sneaky",
                "start_at": event_payload()["start_at"],
                "end_at": event_payload()["end_at"],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_registration_ownership_on_cancel(self):
        self.authenticate(self.participant)
        self.client.post(f"/api/v1/participant/events/{self.event.id}/register/", format="json")
        other = self.create_user("stranger")
        self.authenticate(other)
        response = self.client.post("/api/v1/participant/registrations/1/cancel/")
        self.assertEqual(response.status_code, 404)
