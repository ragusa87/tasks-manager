"""Theme cookie, context processor, and rendering (core.context_processors /
core.views.SetThemeView). Lives here like the other core.* tests
(cf. test_upload_types.py)."""

from django.contrib.auth.models import User
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from core.context_processors import THEME_COOKIE_NAME, theme


class TestThemeContextProcessor(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _request_with_cookie(self, value=None):
        request = self.factory.get("/")
        if value is not None:
            request.COOKIES[THEME_COOKIE_NAME] = value
        return request

    def test_no_cookie_means_system(self):
        self.assertEqual(theme(self._request_with_cookie()), {"THEME": ""})

    def test_valid_values_pass_through(self):
        self.assertEqual(theme(self._request_with_cookie("light")), {"THEME": "light"})
        self.assertEqual(theme(self._request_with_cookie("dark")), {"THEME": "dark"})

    def test_garbage_is_treated_as_system(self):
        self.assertEqual(theme(self._request_with_cookie("blue")), {"THEME": ""})


class TestSetThemeView(TestCase):
    def setUp(self):
        self.client = Client()

    def test_set_light_and_dark(self):
        for value in ("light", "dark"):
            response = self.client.post(reverse("set_theme"), {"theme": value})
            self.assertEqual(response.status_code, 204)
            cookie = response.cookies[THEME_COOKIE_NAME]
            self.assertEqual(cookie.value, value)
            self.assertEqual(cookie["samesite"], "Lax")
            self.assertGreater(int(cookie["max-age"]), 0)

    def test_system_clears_the_cookie(self):
        self.client.cookies[THEME_COOKIE_NAME] = "dark"
        response = self.client.post(reverse("set_theme"), {"theme": "system"})
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.cookies[THEME_COOKIE_NAME]["max-age"], 0)

    def test_garbage_is_rejected(self):
        response = self.client.post(reverse("set_theme"), {"theme": "blue"})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn(THEME_COOKIE_NAME, response.cookies)

    def test_get_is_not_allowed(self):
        response = self.client.get(reverse("set_theme"))
        self.assertEqual(response.status_code, 405)

    def test_works_without_authentication(self):
        response = self.client.post(reverse("set_theme"), {"theme": "dark"})
        self.assertEqual(response.status_code, 204)


class TestThemeRendering(TestCase):
    """The login page is anonymous and extends base.html: it carries the
    data-theme attribute, the toggle, and the theme-color metas."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )

    def test_override_renders_data_theme_and_single_meta(self):
        self.client.cookies[THEME_COOKIE_NAME] = "dark"
        response = self.client.get(reverse("login"))
        self.assertContains(response, 'data-theme="dark"')
        content = response.content.decode()
        self.assertEqual(content.count('name="theme-color"'), 1)

    def test_system_renders_media_paired_metas_and_no_attribute(self):
        response = self.client.get(reverse("login"))
        self.assertNotContains(response, "data-theme=")
        content = response.content.decode()
        self.assertEqual(content.count('name="theme-color"'), 2)
        self.assertIn('media="(prefers-color-scheme: dark)"', content)

    def test_toggle_is_present_for_anonymous_and_authenticated(self):
        response = self.client.get(reverse("login"))
        self.assertContains(response, "data-theme-toggle")
        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "data-theme-toggle")

    def test_offload_page_renders_theme_attribute(self):
        self.client.force_login(self.user)
        self.client.cookies[THEME_COOKIE_NAME] = "light"
        response = self.client.get(reverse("item_offload"))
        self.assertContains(response, 'data-theme="light"')
        self.assertContains(response, "data-theme-toggle")
