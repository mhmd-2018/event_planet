from datetime import timedelta

from django.utils import timezone

from results.models import Result

from .base import BaseAPITestCase


class ResultsAPITests(BaseAPITestCase):

    def setUp(self):
        self.organizer = self.create_user("organizer", role="organizer")
        self.other = self.create_user("other", role="organizer")
        self.event = self.make_event(self.organizer, status="published")
        self.alice = self.create_user("alice")
        self.bob = self.create_user("bob")
        self.results_url = f"/api/v1/organizer/events/{self.event.id}/results/"
        self.public_url = f"/api/v1/public/events/{self.event.id}/results/"

    def create_result(self, payload, user=None, url=None):
        self.authenticate(user or self.organizer)
        return self.client.post(url or self.results_url, payload, format="json")

    def finish(self):
        self.advance(self.event, "closed", "finished")

    # ------------------------------------------------------------- drafts

    def test_owner_creates_draft_result(self):
        response = self.create_result({"participant": self.alice.id, "rank": 1, "score": "9.5"})
        self.assertEqual(response.status_code, 201)
        self.assertIsNone(response.data["publish_at"])
        self.assertEqual(Result.objects.count(), 1)

    def test_result_needs_participant_or_team(self):
        response = self.create_result({"rank": 1})
        self.assertEqual(response.status_code, 400)

    def test_result_rejects_participant_and_team_together(self):
        response = self.create_result(
            {"participant": self.alice.id, "team_name": "Team Nova", "rank": 1}
        )
        self.assertEqual(response.status_code, 400)

    def test_team_only_result_is_valid(self):
        response = self.create_result({"team_name": "Team Nova", "rank": 1})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["team_name"], "Team Nova")

    def test_non_owner_cannot_manage_results(self):
        result = Result.objects.create(event=self.event, participant=self.alice, rank=1)
        self.authenticate(self.other)
        response = self.client.get(f"{self.results_url}{result.id}/")
        self.assertEqual(response.status_code, 404)
        response = self.client.post(
            f"{self.results_url}", {"participant": self.alice.id}, format="json"
        )
        self.assertEqual(response.status_code, 404)

    def test_negative_rank_rejected(self):
        response = self.create_result({"participant": self.alice.id, "rank": 0})
        self.assertEqual(response.status_code, 400)

    # ------------------------------------------------------------ publish

    def test_publish_requires_finished_event(self):
        Result.objects.create(event=self.event, participant=self.alice, rank=1)
        self.authenticate(self.organizer)
        response = self.client.post(f"{self.results_url}1/publish/", format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("finished", str(response.data))

    def test_publish_sets_publish_at(self):
        self.finish()
        result = Result.objects.create(event=self.event, participant=self.alice, rank=1)
        self.authenticate(self.organizer)
        response = self.client.post(f"{self.results_url}{result.id}/publish/", format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.data["publish_at"])
        result.refresh_from_db()
        self.assertTrue(result.is_published)

    def test_publish_all(self):
        self.finish()
        Result.objects.create(event=self.event, participant=self.alice, rank=1)
        Result.objects.create(event=self.event, team_name="Team Nova", rank=2)
        self.authenticate(self.organizer)
        response = self.client.post(f"{self.results_url}publish-all/", format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["published"], 2)
        self.assertEqual(Result.objects.filter(publish_at__isnull=True).count(), 0)

    # ------------------------------------------------------------- public

    def test_public_results_hide_unpublished(self):
        self.finish()
        Result.objects.create(event=self.event, participant=self.alice, rank=1)
        response = self.client.get(self.public_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 0)

    def test_public_results_show_published(self):
        self.finish()
        Result.objects.create(
            event=self.event, participant=self.alice, rank=1, score="9.5000", notes="Flawless"
        )
        Result.objects.create(event=self.event, team_name="Team Nova", rank=2)
        self.authenticate(self.organizer)
        self.assertEqual(self.client.post(f"{self.results_url}publish-all/", format="json").status_code, 200)
        self.logout()

        response = self.client.get(self.public_url)
        rows = response.data["results"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["participant_username"], "alice")
        self.assertEqual(rows[1]["team_name"], "Team Nova")

    def test_public_results_hidden_before_scheduled_time(self):
        self.finish()
        result = Result.objects.create(event=self.event, participant=self.alice, rank=1)
        future = (timezone.now() + timedelta(days=1)).isoformat()
        self.authenticate(self.organizer)
        response = self.client.post(
            f"{self.results_url}{result.id}/publish/", {"publish_at": future}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.logout()
        response = self.client.get(self.public_url)
        self.assertEqual(len(response.data["results"]), 0)

    def test_public_results_404_for_draft_event(self):
        draft = self.make_event(self.organizer, status="draft")
        self.assertEqual(
            self.client.get(f"/api/v1/public/events/{draft.id}/results/").status_code, 404
        )
