from django.test import TestCase, override_settings
from django.urls import reverse

BANNER = "This instance disables uploads and self-resets hourly"


class InstanceBannerTests(TestCase):
    """The banner is driven by settings.INSTANCE_BANNER and rendered site-wide,
    including the (unauthenticated) login page which extends base.html."""

    def test_no_banner_by_default(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, BANNER)

    @override_settings(INSTANCE_BANNER=BANNER)
    def test_banner_shown_when_set(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, BANNER)
