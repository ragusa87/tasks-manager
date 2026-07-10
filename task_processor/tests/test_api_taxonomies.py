import json
from unittest import mock

from django.contrib.auth.models import User
from django.test import Client, TestCase

from task_processor.models import ApiKey, Area, Context, Tag


class TaxonomyEndpointMixin:
    """Shared test grid for the tags/contexts/areas endpoints."""

    url = None
    model = None
    name_max_length = None

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        self.other_user = User.objects.create_user(
            username="otheruser", email="other@example.com", password="testpass"
        )
        _, self.raw_key = ApiKey.generate(self.user, "test key")
        self.headers = {"Authorization": f"Bearer {self.raw_key}"}

    def post_json(self, payload, headers=None):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
            headers=self.headers if headers is None else headers,
        )

    def post_name(self, name, headers=None):
        return self.post_json({"name": name}, headers=headers)

    def test_list_returns_only_own_rows(self):
        self.model.objects.create(name="mine", user=self.user)
        self.model.objects.create(name="theirs", user=self.other_user)
        response = self.client.get(self.url, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        names = [row["name"] for row in response.json()]
        self.assertEqual(names, ["mine"])

    def test_list_without_auth_returns_401(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)

    def test_create_new_returns_201(self):
        response = self.post_name("errand")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["name"], "errand")
        self.assertTrue(
            self.model.objects.filter(user=self.user, name="errand").exists()
        )

    def test_create_existing_returns_200_with_same_id(self):
        existing = self.model.objects.create(name="errand", user=self.user)
        response = self.post_name("errand")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], existing.id)
        self.assertEqual(self.model.objects.filter(user=self.user).count(), 1)

    def test_create_existing_matches_case_insensitively(self):
        existing = self.model.objects.create(name="errand", user=self.user)
        response = self.post_name("ERRAND")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], existing.id)
        self.assertEqual(self.model.objects.filter(user=self.user).count(), 1)

    def test_create_name_owned_by_other_user_returns_201(self):
        self.model.objects.create(name="errand", user=self.other_user)
        response = self.post_name("errand")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.model.objects.filter(name="errand").count(), 2)

    def test_create_blank_name_returns_422(self):
        response = self.post_name("   ")
        self.assertEqual(response.status_code, 422)

    def test_create_too_long_name_returns_422(self):
        response = self.post_name("x" * (self.name_max_length + 1))
        self.assertEqual(response.status_code, 422)

    def test_create_without_auth_returns_401(self):
        response = self.post_name("errand", headers={})
        self.assertEqual(response.status_code, 401)

    def test_create_lost_race_returns_200_with_existing_row(self):
        """Simulate losing the create race: the pre-create lookup sees no
        row, but the (name, user) unique constraint fires on create."""
        existing = self.model.objects.create(name="errand", user=self.user)
        real_filter = self.model.objects.filter
        missed_lookups = []

        def racy_filter(*args, **kwargs):
            if not missed_lookups:
                missed_lookups.append(True)
                return mock.Mock(**{"first.return_value": None})
            return real_filter(*args, **kwargs)

        with mock.patch.object(self.model.objects, "filter", side_effect=racy_filter):
            response = self.post_name("errand")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], existing.id)
        self.assertEqual(self.model.objects.filter(user=self.user).count(), 1)


class DescribedTaxonomyMixin(TaxonomyEndpointMixin):
    """Additional grid for contexts/areas, which carry a description."""

    def test_create_with_description_stores_it(self):
        response = self.post_json({"name": "errand", "description": "runs outside"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["description"], "runs outside")

    def test_create_existing_keeps_original_description(self):
        existing = self.model.objects.create(
            name="errand", user=self.user, description="original"
        )
        response = self.post_json({"name": "errand", "description": "new text"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["description"], "original")
        existing.refresh_from_db()
        self.assertEqual(existing.description, "original")


class TestTagsEndpoint(TaxonomyEndpointMixin, TestCase):
    url = "/api/tags"
    model = Tag
    name_max_length = 50


class TestContextsEndpoint(DescribedTaxonomyMixin, TestCase):
    url = "/api/contexts"
    model = Context
    name_max_length = 100


class TestAreasEndpoint(DescribedTaxonomyMixin, TestCase):
    url = "/api/areas"
    model = Area
    name_max_length = 100
