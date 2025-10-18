from django.contrib.auth.models import User
from django.test import Client, TestCase

from task_processor.constants import GTDStatus, Priority
from task_processor.models import Item


class TestItemViews(TestCase):
    """Test the item views HTTP responses"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )

        self.item = Item.objects.create(
            title="Test item",
            status=GTDStatus.INBOX,
            priority=Priority.NORMAL,
            user=self.user,
        )

    def test_item_update_get_returns_200(self):
        """Test that GET request to item update view returns 200"""
        self.client.force_login(self.user)
        response = self.client.get(f"/item/{self.item.pk}/update/")
        self.assertEqual(response.status_code, 200)

    def test_dashboard_returns_200(self):
        """Test that GET request to item update view returns 200"""
        self.client.force_login(self.user)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_dashboard_search(self):
        """Test that GET request to item update view returns 200"""
        self.client.force_login(self.user)
        response = self.client.get(f"/?q={self.item.title}")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test item")
        self.assertContains(response, "Found 1 result")

        response = self.client.get("/?q=DONTEXIST")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Test item")
        self.assertContains(response, "Found 0 result")
