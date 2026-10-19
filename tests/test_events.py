from datetime import timedelta

from django.utils import timezone

from events.models import Attribute, EventAttributeValue, Stage, StageRole
from registrations.models import Registration

from .base import BaseAPITestCase, event_payload


def stage_payload(**overrides):
    payload = {
        "order": 1,
        "title": "Qualification round",
        "description": "Online qualifiers.",
        "start_at": (timezone.now() + timedelta(days=7)).isoformat(),
        "end_at": (timezone.now() + timedelta(days=8)).isoformat(),
    }
    payload.update(overrides)
    return payload


class EventOrganizerAPITests(BaseAPITestCase):

    def setUp(self):
        self.owner = self.create_user("owner", role="organizer")
        self.other = self.create_user("other", role="organizer")
        self.participant = self.create_user("penny")

    # ------------------------------------------------------------- create

    def test_create_event_defaults_to_draft(self):
        self.authenticate(self.owner)
        response = self.client.post("/api/v1/organizer/events/", event_payload(), format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], "draft")
        self.assertEqual(response.data["owner"], self.owner.id)

    def test_participant_cannot_create_event(self):
        self.authenticate(self.participant)
        response = self.client.post("/api/v1/organizer/events/", event_payload(), format="json")
        self.assertEqual(response.status_code, 403)

    def test_anonymous_cannot_create_event(self):
        response = self.client.post("/api/v1/organizer/events/", event_payload(), format="json")
        self.assertEqual(response.status_code, 401)

    def test_invalid_date_range_rejected(self):
        self.authenticate(self.owner)
        payload = event_payload(
            start_at=(timezone.now() + timedelta(days=9)).isoformat(),
            end_at=(timezone.now() + timedelta(days=7)).isoformat(),
        )
        response = self.client.post("/api/v1/organizer/events/", payload, format="json")
        self.assertEqual(response.status_code, 400)

    def test_zero_capacity_rejected(self):
        self.authenticate(self.owner)
        response = self.client.post(
            "/api/v1/organizer/events/", event_payload(capacity=0), format="json"
        )
        self.assertEqual(response.status_code, 400)

    # --------------------------------------------------------------- edit

    def test_owner_can_edit_event(self):
        event = self.make_event(self.owner)
        self.authenticate(self.owner)
        response = self.client.patch(
            f"/api/v1/organizer/events/{event.id}/", {"title": "Renamed"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        event.refresh_from_db()
        self.assertEqual(event.title, "Renamed")

    def test_non_owner_cannot_edit_event(self):
        event = self.make_event(self.owner)
        self.authenticate(self.other)
        response = self.client.patch(
            f"/api/v1/organizer/events/{event.id}/", {"title": "Hacked"}, format="json"
        )
        self.assertEqual(response.status_code, 404)  # queryset is owner-filtered
        event.refresh_from_db()
        self.assertNotEqual(event.title, "Hacked")

    def test_status_not_writable_via_event_edit(self):
        event = self.make_event(self.owner)
        self.authenticate(self.owner)
        response = self.client.patch(
            f"/api/v1/organizer/events/{event.id}/", {"status": "published"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        event.refresh_from_db()
        self.assertEqual(event.status, "draft")  # unchanged — service layer only

    def test_organizer_lists_only_own_events(self):
        self.make_event(self.owner, title="Mine")
        self.make_event(self.other, title="Theirs")
        self.authenticate(self.owner)
        response = self.client.get("/api/v1/organizer/events/")
        self.assertEqual(response.status_code, 200)
        titles = [row["title"] for row in response.data["results"]]
        self.assertEqual(titles, ["Mine"])

    # ------------------------------------------------------------ status

    def test_status_transitions_forward_only(self):
        event = self.make_event(self.owner)
        self.authenticate(self.owner)
        url = f"/api/v1/organizer/events/{event.id}/status/"

        # Illegal jumps first.
        self.assertEqual(self.client.post(url, {"status": "closed"}, format="json").status_code, 400)
        self.assertEqual(self.client.post(url, {"status": "finished"}, format="json").status_code, 400)

        # Full legal chain: draft -> published -> closed -> finished.
        self.assertEqual(self.client.post(url, {"status": "published"}, format="json").status_code, 200)
        # No repeated/illegal steps.
        self.assertEqual(self.client.post(url, {"status": "published"}, format="json").status_code, 400)
        self.assertEqual(self.client.post(url, {"status": "finished"}, format="json").status_code, 400)
        self.assertEqual(self.client.post(url, {"status": "closed"}, format="json").status_code, 200)
        self.assertEqual(self.client.post(url, {"status": "finished"}, format="json").status_code, 200)
        # Terminal.
        self.assertEqual(self.client.post(url, {"status": "published"}, format="json").status_code, 400)

        event.refresh_from_db()
        self.assertEqual(event.status, "finished")

    def test_status_change_requires_owner(self):
        event = self.make_event(self.owner)
        self.authenticate(self.other)
        response = self.client.post(
            f"/api/v1/organizer/events/{event.id}/status/", {"status": "published"}, format="json"
        )
        self.assertEqual(response.status_code, 404)
        event.refresh_from_db()
        self.assertEqual(event.status, "draft")

    def test_status_change_requires_organizer_role(self):
        event = self.make_event(self.owner)
        self.authenticate(self.participant)
        response = self.client.post(
            f"/api/v1/organizer/events/{event.id}/status/", {"status": "published"}, format="json"
        )
        self.assertEqual(response.status_code, 403)

    # -------------------------------------------------------- participants

    def test_participants_action_owner_only(self):
        event = self.make_event(self.owner, status="published")
        Registration.objects.create(event=event, participant=self.participant)

        self.authenticate(self.owner)
        response = self.client.get(f"/api/v1/organizer/events/{event.id}/participants/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["participant_username"], "penny")

        self.authenticate(self.other)
        response = self.client.get(f"/api/v1/organizer/events/{event.id}/participants/")
        self.assertEqual(response.status_code, 404)


class PublicEventAPITests(BaseAPITestCase):

    def setUp(self):
        self.owner = self.create_user("owner", role="organizer")

    def test_public_list_shows_only_visible_events(self):
        self.make_event(self.owner, status="draft", title="Hidden")
        self.make_event(self.owner, status="published", title="Visible")
        response = self.client.get("/api/v1/public/events/")
        self.assertEqual(response.status_code, 200)
        titles = [row["title"] for row in response.data["results"]]
        self.assertEqual(titles, ["Visible"])

    def test_public_detail_draft_is_404(self):
        event = self.make_event(self.owner, status="draft")
        self.assertEqual(self.client.get(f"/api/v1/public/events/{event.id}/").status_code, 404)

    def test_public_detail_visible_for_published_closed_finished(self):
        event = self.make_event(self.owner, status="draft")
        url = f"/api/v1/public/events/{event.id}/"
        for status in ("published", "closed", "finished"):
            event.status = status
            event.save()
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, status)
            self.assertEqual(response.data["status"], status)

    def test_public_detail_includes_stages_and_attribute_values(self):
        event = self.make_event(self.owner, status="published")
        Stage.objects.create(
            event=event, order=1, title="Opening", start_at=event.start_at, end_at=event.end_at
        )
        attribute = Attribute.objects.create(name="Venue", key="venue", data_type="text")
        EventAttributeValue.objects.create(event=event, attribute=attribute, value_text="Mars Dome")

        response = self.client.get(f"/api/v1/public/events/{event.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["stages"][0]["title"], "Opening")
        self.assertEqual(response.data["attribute_values"][0]["value"], "Mars Dome")

    def test_public_list_search_and_registration_counts(self):
        event = self.make_event(self.owner, status="published", capacity=10, title="Space Race")
        Registration.objects.create(event=event, participant=self.create_user("a"))
        Registration.objects.create(event=event, participant=self.create_user("b"))

        response = self.client.get("/api/v1/public/events/", {"search": "space"})
        self.assertEqual(response.status_code, 200)
        row = response.data["results"][0]
        self.assertEqual(row["registered_count"], 2)
        self.assertEqual(row["spots_left"], 8)

        response = self.client.get("/api/v1/public/events/", {"search": "nomatch"})
        self.assertEqual(len(response.data["results"]), 0)


class StageAPITests(BaseAPITestCase):

    def setUp(self):
        self.owner = self.create_user("owner", role="organizer")
        self.other = self.create_user("other", role="organizer")
        self.event = self.make_event(self.owner, status="published")

    def test_owner_creates_stage(self):
        self.authenticate(self.owner)
        response = self.client.post(
            f"/api/v1/organizer/events/{self.event.id}/stages/", stage_payload(), format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["order"], 1)

    def test_duplicate_stage_order_rejected(self):
        Stage.objects.create(
            event=self.event, order=1, title="S1",
            start_at=self.event.start_at, end_at=self.event.end_at,
        )
        self.authenticate(self.owner)
        response = self.client.post(
            f"/api/v1/organizer/events/{self.event.id}/stages/", stage_payload(), format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_invalid_stage_dates_rejected(self):
        self.authenticate(self.owner)
        payload = stage_payload(
            start_at=(timezone.now() + timedelta(days=8)).isoformat(),
            end_at=(timezone.now() + timedelta(days=7)).isoformat(),
        )
        response = self.client.post(
            f"/api/v1/organizer/events/{self.event.id}/stages/", payload, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_non_owner_cannot_touch_stages(self):
        self.authenticate(self.other)
        response = self.client.post(
            f"/api/v1/organizer/events/{self.event.id}/stages/", stage_payload(), format="json"
        )
        self.assertEqual(response.status_code, 404)  # event not owned -> hidden

    def test_stage_role_flow(self):
        stage = Stage.objects.create(
            event=self.event, order=1, title="Finals",
            start_at=self.event.start_at, end_at=self.event.end_at,
        )
        judge = self.create_user("judgey")
        self.authenticate(self.owner)

        url = f"/api/v1/organizer/events/{self.event.id}/stages/{stage.id}/roles/"
        response = self.client.post(url, {"user": judge.id, "role": "judge"}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["user_username"], "judgey")

        # Same user, same stage -> unique (stage, user) violation.
        response = self.client.post(url, {"user": judge.id, "role": "moderator"}, format="json")
        self.assertEqual(response.status_code, 400)

        response = self.client.post(url, {"user": judge.id, "role": "astronaut"}, format="json")
        self.assertEqual(response.status_code, 400)  # invalid choice

        listing = self.client.get(url)
        self.assertEqual(listing.status_code, 200)
        role_id = listing.data["results"][0]["id"]
        self.assertEqual(self.client.delete(f"{url}{role_id}/").status_code, 204)
        self.assertEqual(StageRole.objects.filter(stage=stage).count(), 0)

    def test_stage_role_requires_ownership(self):
        stage = Stage.objects.create(
            event=self.event, order=1, title="Finals",
            start_at=self.event.start_at, end_at=self.event.end_at,
        )
        judge = self.create_user("judgey")
        self.authenticate(self.other)
        url = f"/api/v1/organizer/events/{self.event.id}/stages/{stage.id}/roles/"
        response = self.client.post(url, {"user": judge.id, "role": "judge"}, format="json")
        self.assertEqual(response.status_code, 404)
