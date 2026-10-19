from events.models import Attribute, AttributeOption, EventAttributeValue

from .base import BaseAPITestCase


def choice_options(*values):
    return [{"value": value, "order": index} for index, value in enumerate(values)]


class AttributeCatalogAPITests(BaseAPITestCase):

    def setUp(self):
        self.organizer = self.create_user("organizer", role="organizer")
        self.authenticate(self.organizer)

    def create_attribute(self, payload):
        return self.client.post("/api/v1/organizer/attributes/", payload, format="json")

    def test_create_text_attribute_auto_generates_key(self):
        response = self.create_attribute({"name": "Difficulty Level", "data_type": "text"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["key"], "difficulty-level")
        self.assertEqual(response.data["data_type"], "text")

    def test_duplicate_key_rejected(self):
        self.create_attribute({"name": "Venue", "key": "venue", "data_type": "text"})
        response = self.create_attribute({"name": "Other", "key": "venue", "data_type": "text"})
        self.assertEqual(response.status_code, 400)

    def test_choice_attribute_requires_options(self):
        response = self.create_attribute({"name": "Level", "data_type": "choice"})
        self.assertEqual(response.status_code, 400)

    def test_choice_attribute_with_options(self):
        response = self.create_attribute(
            {
                "name": "Skill level",
                "data_type": "choice",
                "options": choice_options("Beginner", "Advanced"),
            }
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual([option["value"] for option in response.data["options"]], ["Beginner", "Advanced"])

    def test_options_rejected_for_non_choice_type(self):
        response = self.create_attribute(
            {
                "name": "Seats",
                "data_type": "integer",
                "options": choice_options("A", "B"),
            }
        )
        self.assertEqual(response.status_code, 400)

    def test_update_replaces_options(self):
        created = self.create_attribute(
            {
                "name": "Skill level",
                "data_type": "choice",
                "options": choice_options("Beginner", "Advanced"),
            }
        )
        attribute_id = created.data["id"]
        response = self.client.patch(
            f"/api/v1/organizer/attributes/{attribute_id}/",
            {"options": choice_options("Novice", "Pro")},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        values = {option["value"] for option in response.data["options"]}
        self.assertEqual(values, {"Novice", "Pro"})

    def test_duplicate_option_values_rejected(self):
        """Duplicate values inside one payload would hit a DB unique constraint -> 500."""
        response = self.create_attribute(
            {
                "name": "Level",
                "data_type": "choice",
                "options": choice_options("A", "A"),
            }
        )
        self.assertEqual(response.status_code, 400)


class AttributeOptionSafetyTests(BaseAPITestCase):
    """Option/data-type edits must never silently destroy bound event values."""

    def setUp(self):
        self.organizer = self.create_user("organizer", role="organizer")
        self.event = self.make_event(self.organizer, status="published")
        self.authenticate(self.organizer)

    def _create_choice_attribute(self):
        created = self.client.post(
            "/api/v1/organizer/attributes/",
            {
                "name": "Level",
                "data_type": "choice",
                "options": choice_options("Beginner", "Advanced"),
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        return Attribute.objects.get(pk=created.data["id"])

    def test_removing_referenced_option_is_blocked_not_cascaded(self):
        attribute = self._create_choice_attribute()
        beginner = AttributeOption.objects.get(attribute=attribute, value="Beginner")
        EventAttributeValue.objects.create(
            event=self.event, attribute=attribute, value_option=beginner
        )

        response = self.client.patch(
            f"/api/v1/organizer/attributes/{attribute.id}/",
            {"options": choice_options("Novice", "Pro")},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        # The bound event value survived.
        self.assertEqual(EventAttributeValue.objects.count(), 1)
        self.assertEqual(EventAttributeValue.objects.get().value_option.value, "Beginner")

    def test_keeping_referenced_option_updates_without_data_loss(self):
        attribute = self._create_choice_attribute()
        beginner = AttributeOption.objects.get(attribute=attribute, value="Beginner")
        EventAttributeValue.objects.create(
            event=self.event, attribute=attribute, value_option=beginner
        )

        response = self.client.patch(
            f"/api/v1/organizer/attributes/{attribute.id}/",
            {"options": choice_options("Beginner", "Pro")},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(EventAttributeValue.objects.count(), 1)
        self.assertEqual(EventAttributeValue.objects.get().value_option.value, "Beginner")

    def test_data_type_change_with_bound_values_rejected(self):
        attribute = Attribute.objects.create(name="Seats", key="seats2", data_type="integer")
        EventAttributeValue.objects.create(
            event=self.event, attribute=attribute, value_integer=3
        )
        response = self.client.patch(
            f"/api/v1/organizer/attributes/{attribute.id}/",
            {"data_type": "text"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        attribute.refresh_from_db()
        self.assertEqual(attribute.data_type, "integer")
        self.assertEqual(EventAttributeValue.objects.get().value_integer, 3)


class EventAttributeValueAPITests(BaseAPITestCase):

    def setUp(self):
        self.organizer = self.create_user("organizer", role="organizer")
        self.other = self.create_user("other", role="organizer")
        self.event = self.make_event(self.organizer, status="published")
        self.values_url = f"/api/v1/organizer/events/{self.event.id}/attribute-values/"

    def set_value(self, attribute, value, url=None, user=None):
        self.authenticate(user or self.organizer)
        return self.client.post(
            url or self.values_url, {"attribute": attribute.id, "value": value}, format="json"
        )

    # ------------------------------------------------------ typed values

    def test_integer_value_accepted_and_invalid_rejected(self):
        attribute = Attribute.objects.create(name="Seats", key="seats", data_type="integer")
        self.assertEqual(self.set_value(attribute, 4).status_code, 201)
        self.assertEqual(self.set_value(attribute, "abc").status_code, 400)
        self.assertEqual(self.set_value(attribute, True).status_code, 400)

    def test_text_value(self):
        attribute = Attribute.objects.create(name="Venue", key="venue", data_type="text")
        response = self.set_value(attribute, "Mars Dome")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["value"], "Mars Dome")

    def test_decimal_value(self):
        attribute = Attribute.objects.create(name="Fee", key="fee", data_type="decimal")
        response = self.set_value(attribute, "9.5")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(float(response.data["value"]), 9.5)

    def test_decimal_out_of_range_rejected_not_500(self):
        """value_decimal is max_digits=14 / decimal_places=4; overflow must be a 400."""
        attribute = Attribute.objects.create(name="Fee2", key="fee2", data_type="decimal")
        self.assertEqual(self.set_value(attribute, "0.00001").status_code, 400)  # 5 dp
        self.assertEqual(self.set_value(attribute, "1e30").status_code, 400)  # 31 int digits
        self.assertEqual(self.set_value(attribute, "123456789012345").status_code, 400)
        # Boundary values are still fine (14 digits total, 4 decimal places).
        self.assertEqual(self.set_value(attribute, "99999999.9999").status_code, 201)

    def test_boolean_coercion(self):
        attribute = Attribute.objects.create(name="Online", key="online", data_type="boolean")
        response = self.set_value(attribute, "true")
        self.assertEqual(response.status_code, 201)
        self.assertIs(response.data["value"], True)
        self.assertEqual(self.set_value(attribute, "maybe").status_code, 400)

    def test_date_value(self):
        attribute = Attribute.objects.create(name="Deadline", key="deadline", data_type="date")
        self.assertEqual(self.set_value(attribute, "2026-09-15").status_code, 201)
        response = self.set_value(attribute, "15/09/2026")
        self.assertEqual(response.status_code, 400)

    def test_choice_value_valid_and_invalid(self):
        attribute = Attribute.objects.create(name="Level", key="level", data_type="choice")
        from events.models import AttributeOption

        beginner = AttributeOption.objects.create(attribute=attribute, value="Beginner")
        AttributeOption.objects.create(attribute=attribute, value="Advanced")

        response = self.set_value(attribute, "Beginner")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["value"], "Beginner")
        self.assertEqual(response.data["attribute"]["key"], "level")

        response = self.set_value(attribute, "Expert")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Allowed options", str(response.data["value"]))

    # ------------------------------------------------------ required / upsert

    def test_required_attribute_rejects_empty_value(self):
        attribute = Attribute.objects.create(
            name="Sponsor", key="sponsor", data_type="text", required=True
        )
        self.assertEqual(self.set_value(attribute, "").status_code, 400)
        self.assertEqual(self.set_value(attribute, None).status_code, 400)
        self.assertEqual(self.set_value(attribute, "Acme").status_code, 201)

    def test_upsert_updates_same_row(self):
        attribute = Attribute.objects.create(name="Venue", key="venue", data_type="text")
        self.assertEqual(self.set_value(attribute, "Old Dome").status_code, 201)
        response = self.set_value(attribute, "New Dome")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(EventAttributeValue.objects.filter(attribute=attribute).count(), 1)
        self.assertEqual(EventAttributeValue.objects.get(attribute=attribute).value_text, "New Dome")

    def test_non_owner_cannot_set_value(self):
        attribute = Attribute.objects.create(name="Venue", key="venue", data_type="text")
        response = self.set_value(attribute, "Nope", user=self.other)
        self.assertEqual(response.status_code, 404)  # event not owned -> hidden

    def test_delete_value(self):
        attribute = Attribute.objects.create(name="Venue", key="venue", data_type="text")
        created = self.set_value(attribute, "Mars Dome")
        response = self.client.delete(f"{self.values_url}{created.data['id']}/")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(EventAttributeValue.objects.count(), 0)

    def test_public_detail_exposes_values(self):
        attribute = Attribute.objects.create(name="Venue", key="venue", data_type="text")
        self.set_value(attribute, "Mars Dome")
        response = self.client.get(f"/api/v1/public/events/{self.event.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["attribute_values"][0]["value"], "Mars Dome")
