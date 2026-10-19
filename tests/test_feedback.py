from registrations.models import Feedback, Registration

from .base import BaseAPITestCase


class FeedbackAPITests(BaseAPITestCase):

    def setUp(self):
        self.organizer = self.create_user("organizer", role="organizer")
        self.event = self.make_event(self.organizer, status="published")
        self.alice = self.create_user("alice")
        self.bob = self.create_user("bob")
        self.outsider = self.create_user("carol")

    def register_alice(self):
        Registration.objects.create(event=self.event, participant=self.alice)

    def feedback(self, user, rating=5, text="Great event!", event=None):
        self.authenticate(user)
        return self.client.post(
            f"/api/v1/participant/events/{(event or self.event).id}/feedback/",
            {"rating": rating, "text": text},
            format="json",
        )

    # ------------------------------------------------------- gating rules

    def test_feedback_before_finished_rejected(self):
        self.register_alice()
        # Event is only published -> permission layer rejects with 403.
        response = self.feedback(self.alice)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Feedback.objects.count(), 0)

    def test_feedback_requires_registration(self):
        self.advance(self.event, "closed", "finished")
        response = self.feedback(self.outsider)  # never registered
        self.assertEqual(response.status_code, 403)

    def test_feedback_success_after_finished(self):
        self.register_alice()
        self.advance(self.event, "closed", "finished")
        response = self.feedback(self.alice, rating=4, text="Loved it")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["rating"], 4)
        self.assertEqual(Feedback.objects.count(), 1)

    # ------------------------------------------------------------- upsert

    def test_feedback_resubmission_updates_single_row(self):
        self.register_alice()
        self.advance(self.event, "closed", "finished")
        self.assertEqual(self.feedback(self.alice, rating=2, text="meh").status_code, 201)
        response = self.feedback(self.alice, rating=5, text="actually amazing")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Feedback.objects.count(), 1)
        feedback = Feedback.objects.get()
        self.assertEqual(feedback.rating, 5)
        self.assertEqual(feedback.text, "actually amazing")

    # ------------------------------------------------------------- limits

    def test_rating_bounds_rejected(self):
        self.register_alice()
        self.advance(self.event, "closed", "finished")
        self.assertEqual(self.feedback(self.alice, rating=0).status_code, 400)
        self.assertEqual(self.feedback(self.alice, rating=6).status_code, 400)

    def test_organizer_cannot_submit_feedback(self):
        response = self.feedback(self.organizer)
        self.assertEqual(response.status_code, 403)

    # ------------------------------------------------- organizer visibility

    def test_organizer_can_view_event_feedback(self):
        """Spec: the organizer must be able to view feedback for their event."""
        self.register_alice()
        Registration.objects.create(event=self.event, participant=self.bob)
        self.advance(self.event, "closed", "finished")
        self.feedback(self.alice, rating=4, text="Loved it")
        self.feedback(self.bob, rating=2, text="Okay-ish")

        self.authenticate(self.organizer)
        response = self.client.get(f"/api/v1/organizer/events/{self.event.id}/feedback/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)
        ratings = sorted(row["rating"] for row in response.data)
        self.assertEqual(ratings, [2, 4])
        usernames = {row["participant_username"] for row in response.data}
        self.assertEqual(usernames, {"alice", "bob"})

    def test_feedback_listing_owner_only(self):
        self.register_alice()
        self.advance(self.event, "closed", "finished")
        self.feedback(self.alice)

        stranger_organizer = self.create_user("other_org", role="organizer")
        self.authenticate(stranger_organizer)
        response = self.client.get(f"/api/v1/organizer/events/{self.event.id}/feedback/")
        self.assertEqual(response.status_code, 404)  # not their event -> hidden

    def test_participant_cannot_view_organizer_feedback_listing(self):
        self.register_alice()
        self.advance(self.event, "closed", "finished")
        self.feedback(self.alice)

        self.authenticate(self.bob)
        response = self.client.get(f"/api/v1/organizer/events/{self.event.id}/feedback/")
        self.assertEqual(response.status_code, 403)

    def test_feedback_event_404(self):
        self.authenticate(self.alice)
        response = self.client.post(
            "/api/v1/participant/events/424242/feedback/",
            {"rating": 5},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
