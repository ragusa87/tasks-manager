from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.utils import timezone

from task_processor.models import ApiKey


class TestApiKeyModel(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )

    def test_generate_returns_raw_key_and_stores_only_hash(self):
        api_key, raw_key = ApiKey.generate(self.user, "test key")
        self.assertNotEqual(api_key.hashed_key, raw_key)
        self.assertEqual(api_key.hashed_key, ApiKey.hash_key(raw_key))
        self.assertEqual(api_key.prefix, raw_key[:8])
        self.assertTrue(api_key.is_active)
        self.assertIsNone(api_key.last_used_at)

    def test_authenticate_returns_key_and_bumps_last_used_at(self):
        api_key, raw_key = ApiKey.generate(self.user, "test key")
        authenticated = ApiKey.authenticate(raw_key)
        self.assertEqual(authenticated.pk, api_key.pk)
        self.assertEqual(authenticated.user, self.user)
        api_key.refresh_from_db()
        self.assertIsNotNone(api_key.last_used_at)

    def test_authenticate_within_window_does_not_bump_last_used_at(self):
        api_key, raw_key = ApiKey.generate(self.user, "test key")
        ApiKey.authenticate(raw_key)
        api_key.refresh_from_db()
        first_seen = api_key.last_used_at
        ApiKey.authenticate(raw_key)
        api_key.refresh_from_db()
        self.assertEqual(api_key.last_used_at, first_seen)

    def test_authenticate_bumps_stale_last_used_at(self):
        api_key, raw_key = ApiKey.generate(self.user, "test key")
        stale = (
            timezone.now()
            - settings.API_KEY_LAST_USED_UPDATE_INTERVAL
            - timedelta(minutes=1)
        )
        ApiKey.objects.filter(pk=api_key.pk).update(last_used_at=stale)
        ApiKey.authenticate(raw_key)
        api_key.refresh_from_db()
        self.assertGreater(api_key.last_used_at, stale)

    def test_authenticate_wrong_key_returns_none(self):
        ApiKey.generate(self.user, "test key")
        self.assertIsNone(ApiKey.authenticate("bogus-key"))

    def test_authenticate_inactive_key_returns_none(self):
        api_key, raw_key = ApiKey.generate(self.user, "test key")
        api_key.is_active = False
        api_key.save()
        self.assertIsNone(ApiKey.authenticate(raw_key))

    def test_authenticate_inactive_user_returns_none(self):
        _, raw_key = ApiKey.generate(self.user, "test key")
        self.user.is_active = False
        self.user.save()
        self.assertIsNone(ApiKey.authenticate(raw_key))


class TestApiAuthentication(TestCase):
    """HTTP-level auth checks, using GET /api/items as representative endpoint."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        self.api_key, self.raw_key = ApiKey.generate(self.user, "test key")

    def test_missing_header_returns_401(self):
        response = self.client.get("/api/items")
        self.assertEqual(response.status_code, 401)

    def test_bogus_key_returns_401(self):
        response = self.client.get(
            "/api/items", headers={"Authorization": "Bearer bogus"}
        )
        self.assertEqual(response.status_code, 401)

    def test_wrong_scheme_returns_401(self):
        response = self.client.get(
            "/api/items", headers={"Authorization": f"Basic {self.raw_key}"}
        )
        self.assertEqual(response.status_code, 401)

    def test_revoked_key_returns_401(self):
        self.api_key.is_active = False
        self.api_key.save()
        response = self.client.get(
            "/api/items", headers={"Authorization": f"Bearer {self.raw_key}"}
        )
        self.assertEqual(response.status_code, 401)

    def test_inactive_user_key_returns_401(self):
        self.user.is_active = False
        self.user.save()
        response = self.client.get(
            "/api/items", headers={"Authorization": f"Bearer {self.raw_key}"}
        )
        self.assertEqual(response.status_code, 401)

    def test_valid_key_returns_200(self):
        response = self.client.get(
            "/api/items", headers={"Authorization": f"Bearer {self.raw_key}"}
        )
        self.assertEqual(response.status_code, 200)
