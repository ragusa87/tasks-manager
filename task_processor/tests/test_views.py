from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from task_processor.constants import GTDStatus, Priority
from task_processor.models import Area, Context, Item, Tag


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

    def test_item_create_get_returns_200(self):
        """Test that GET request to item create view returns 200"""
        self.client.force_login(self.user)
        response = self.client.get(reverse("item_create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create New Item")

    def test_item_create_post_creates_item(self):
        """Test that POST request to item create view creates a new item"""
        self.client.force_login(self.user)

        # Create a context for testing
        context = Context.objects.create(name="Test Context", user=self.user)

        # Count items before creation
        initial_count = Item.objects.count()

        # POST data matching the curl command
        post_data = {
            "title": "dvdfvd",
            "description": "vfdv",
            "contexts": str(context.id),
            "area": "",
            "tags": "",
            "parent": "",
            "priority": Priority.NORMAL,
            "due_date": "",
            "start_date": "",
            "estimated_duration": "",
            "energy": "",
            "remind_at": "",
            "rrule": "",
        }

        response = self.client.post(reverse("item_create"), data=post_data)

        # Should redirect on success
        self.assertEqual(response.status_code, 302)

        # Verify item was created
        self.assertEqual(Item.objects.count(), initial_count + 1)

        # Get the newly created item
        new_item = Item.objects.latest("created_at")

        # Verify item properties
        self.assertEqual(new_item.title, "dvdfvd")
        self.assertEqual(new_item.description, "vfdv")
        self.assertEqual(new_item.priority, Priority.NORMAL)
        self.assertEqual(new_item.user, self.user)
        self.assertEqual(new_item.status, GTDStatus.INBOX)

        # Verify ManyToMany relationship
        self.assertIn(context, new_item.contexts.all())

    def test_item_create_post_with_multiple_contexts(self):
        """Test creating an item with multiple contexts"""
        self.client.force_login(self.user)

        # Create multiple contexts
        context1 = Context.objects.create(name="Context 1", user=self.user)
        context2 = Context.objects.create(name="Context 2", user=self.user)

        post_data = {
            "title": "Test Item with Multiple Contexts",
            "description": "Test description",
            "contexts": f"{context1.id},{context2.id}",
            "area": "",
            "tags": "",
            "parent": "",
            "priority": Priority.NORMAL,
            "due_date": "",
            "start_date": "",
            "estimated_duration": "",
            "energy": "",
            "remind_at": "",
            "rrule": "",
        }

        response = self.client.post(reverse("item_create"), data=post_data)
        self.assertEqual(response.status_code, 302)

        # Get the newly created item
        new_item = Item.objects.latest("created_at")

        # Verify both contexts are associated
        self.assertEqual(new_item.contexts.count(), 2)
        self.assertIn(context1, new_item.contexts.all())
        self.assertIn(context2, new_item.contexts.all())

    def test_item_create_post_with_area_and_tags(self):
        """Test creating an item with area and tags"""
        self.client.force_login(self.user)

        # Create an area and tags
        area = Area.objects.create(name="Test Area", user=self.user)
        tag1 = Tag.objects.create(name="urgent", user=self.user)
        tag2 = Tag.objects.create(name="important", user=self.user)

        post_data = {
            "title": "Item with Area and Tags",
            "description": "Test description",
            "contexts": "",
            "area": area.id,
            "tags": f"{tag1.id},{tag2.id}",
            "parent": "",
            "priority": Priority.HIGH,
            "due_date": "",
            "start_date": "",
            "estimated_duration": "",
            "energy": "",
            "remind_at": "",
            "rrule": "",
        }

        response = self.client.post(reverse("item_create"), data=post_data)
        self.assertEqual(response.status_code, 302)

        # Get the newly created item
        new_item = Item.objects.latest("created_at")

        # Verify area and tags
        self.assertEqual(new_item.area, area)
        self.assertEqual(new_item.tags.count(), 2)
        self.assertIn(tag1, new_item.tags.all())
        self.assertIn(tag2, new_item.tags.all())
        self.assertEqual(new_item.priority, Priority.HIGH)

    def test_item_create_post_requires_title(self):
        """Test that title is required when creating an item"""
        self.client.force_login(self.user)

        post_data = {
            "title": "",  # Empty title
            "description": "Test description",
            "contexts": "",
            "area": "",
            "tags": "",
            "parent": "",
            "priority": Priority.NORMAL,
            "due_date": "",
            "start_date": "",
            "estimated_duration": "",
            "energy": "",
            "remind_at": "",
            "rrule": "",
        }

        initial_count = Item.objects.count()
        response = self.client.post(reverse("item_create"), data=post_data)

        # Should not redirect, should show form with errors
        self.assertEqual(response.status_code, 200)

        # No new item should be created
        self.assertEqual(Item.objects.count(), initial_count)

        # Should contain error message
        self.assertContains(response, "This field is required")

    def test_item_create_requires_authentication(self):
        """Test that item create requires authentication"""
        # Don't log in
        response = self.client.get(reverse("item_create"))

        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)
