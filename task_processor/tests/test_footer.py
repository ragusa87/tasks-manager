from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse


class FooterTests(TestCase):
    """The footer partial renders on pages extending base.html."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_footer_shows_license_and_copyright(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Laurent Constantin")
        self.assertContains(response, "AGPL-3.0")

    def test_footer_links_to_github(self):
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "https://github.com/ragusa87/tasks-manager")
