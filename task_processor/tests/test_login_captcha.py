import importlib
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import NoReverseMatch, clear_url_caches, reverse

import core.urls
import task_processor.urls
from core import captcha
from task_processor.constants import DEMO_ACCOUNTS

CAPTCHA_ON = dict(
    LOGIN_CAPTCHA_ENABLED=True,
    TURNSTILE_SITE_KEY="site-key",
    TURNSTILE_SECRET_KEY="secret-key",
)


def _response(success):
    """A stub mimicking requests.Response.json()."""

    class _Stub:
        def json(self):
            return {"success": success}

    return _Stub()


class CaptchaHelperTests(TestCase):
    def test_disabled_by_default(self):
        self.assertFalse(captcha.captcha_enabled())

    @override_settings(LOGIN_CAPTCHA_ENABLED=True)
    def test_disabled_without_keys(self):
        # Flag on but keys missing → still disabled (cannot arm half-configured).
        self.assertFalse(captcha.captcha_enabled())

    @override_settings(**CAPTCHA_ON)
    def test_enabled_with_flag_and_keys(self):
        self.assertTrue(captcha.captcha_enabled())

    def test_verify_is_noop_when_disabled(self):
        # Disabled → always passes, without any network call.
        with patch("core.captcha.requests.post") as post:
            self.assertTrue(captcha.verify_turnstile("anything"))
            post.assert_not_called()

    @override_settings(**CAPTCHA_ON)
    def test_verify_requires_a_token(self):
        with patch("core.captcha.requests.post") as post:
            self.assertFalse(captcha.verify_turnstile(""))
            post.assert_not_called()

    @override_settings(**CAPTCHA_ON)
    def test_verify_success(self):
        with patch("core.captcha.requests.post", return_value=_response(True)):
            self.assertTrue(captcha.verify_turnstile("token", "1.2.3.4"))

    @override_settings(**CAPTCHA_ON)
    def test_verify_rejected(self):
        with patch("core.captcha.requests.post", return_value=_response(False)):
            self.assertFalse(captcha.verify_turnstile("token"))

    @override_settings(**CAPTCHA_ON)
    def test_verify_fails_closed_on_network_error(self):
        import requests

        with patch("core.captcha.requests.post", side_effect=requests.RequestException):
            self.assertFalse(captcha.verify_turnstile("token"))


class LoginCaptchaViewTests(TestCase):
    def setUp(self):
        self.url = reverse("login")
        self.user = User.objects.create_user(username="alice", password="pw")

    def test_login_works_without_captcha_by_default(self):
        response = self.client.post(self.url, {"username": "alice", "password": "pw"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)

    @override_settings(**CAPTCHA_ON)
    def test_widget_rendered_when_enabled(self):
        response = self.client.get(self.url)
        self.assertContains(response, "cf-turnstile")
        self.assertContains(response, "site-key")

    @override_settings(**CAPTCHA_ON)
    def test_no_widget_when_disabled(self):
        with override_settings(LOGIN_CAPTCHA_ENABLED=False):
            response = self.client.get(self.url)
        self.assertNotContains(response, "cf-turnstile")

    @override_settings(**CAPTCHA_ON)
    def test_login_blocked_when_captcha_missing(self):
        response = self.client.post(self.url, {"username": "alice", "password": "pw"})
        self.assertEqual(response.status_code, 200)  # re-rendered with the error
        self.assertNotIn("_auth_user_id", self.client.session)

    @override_settings(**CAPTCHA_ON)
    def test_login_succeeds_with_valid_captcha(self):
        with patch("core.captcha.requests.post", return_value=_response(True)):
            response = self.client.post(
                self.url,
                {
                    "username": "alice",
                    "password": "pw",
                    "cf-turnstile-response": "token",
                },
            )
        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)

    @override_settings(**CAPTCHA_ON)
    def test_bad_credentials_still_need_captcha_first(self):
        # A wrong password with a failing captcha reports the captcha error and
        # never reaches authenticate().
        with patch("core.captcha.requests.post", return_value=_response(False)):
            response = self.client.post(
                self.url,
                {
                    "username": "alice",
                    "password": "wrong",
                    "cf-turnstile-response": "x",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    @override_settings(IS_DEMO=True, **CAPTCHA_ON)
    def test_demo_buttons_link_to_captcha_page_when_armed(self):
        response = self.client.get(self.url)
        self.assertContains(response, reverse("demo_login", args=["user1"]))


# The hand-off page only exists when it is actually needed: a demo instance
# with the captcha armed. Every other combination 404s.
@override_settings(IS_DEMO=True, **CAPTCHA_ON)
class DemoLoginViewTests(TestCase):
    def setUp(self):
        # Drive the test from the real source of truth, so it follows any change
        # to the seeded demo accounts (exactly what fixturize seeds).
        self.username, self.password = DEMO_ACCOUNTS[0]
        self.user = User.objects.create_user(
            username=self.username, password=self.password
        )
        self.url = reverse("demo_login", args=[self.username])

    def test_get_renders_page_with_widget(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"Continue as {self.username}")
        self.assertContains(response, "cf-turnstile")

    def test_unknown_demo_user_is_404(self):
        response = self.client.get(reverse("demo_login", args=["nope"]))
        self.assertEqual(response.status_code, 404)

    @override_settings(IS_DEMO=False)
    def test_404_when_not_a_demo_instance(self):
        self.assertEqual(self.client.get(self.url).status_code, 404)

    @override_settings(LOGIN_CAPTCHA_ENABLED=False)
    def test_404_when_captcha_is_off(self):
        # Not reachable when the captcha is disabled — no passwordless login
        # endpoint hanging around; the login page uses one-click buttons then.
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url).status_code, 404)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_post_requires_captcha(self):
        response = self.client.post(self.url)  # no token
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_post_logs_in_with_valid_captcha(self):
        with patch("core.captcha.requests.post", return_value=_response(True)):
            response = self.client.post(self.url, {"cf-turnstile-response": "token"})
        self.assertRedirects(response, reverse("dashboard"))
        self.assertIn("_auth_user_id", self.client.session)


class DemoLoginRouteRegistrationTests(TestCase):
    """The route must not even be registered on a non-demo instance."""

    def _reload_urlconf(self):
        clear_url_caches()
        importlib.reload(task_processor.urls)
        importlib.reload(core.urls)
        clear_url_caches()

    def tearDown(self):
        # Restore the pinned (IS_DEMO=True) URLconf for the rest of the suite.
        self._reload_urlconf()

    def test_route_present_on_demo_instance(self):
        with override_settings(IS_DEMO=True):
            self._reload_urlconf()
            self.assertTrue(reverse("demo_login", args=["user1"]))

    def test_route_absent_on_non_demo_instance(self):
        with override_settings(IS_DEMO=False):
            self._reload_urlconf()
            with self.assertRaises(NoReverseMatch):
                reverse("demo_login", args=["user1"])
