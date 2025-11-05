from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from task_processor.forms import TagForm
from task_processor.models import Tag


class TagFormTests(TestCase):
    """Test the TagForm validation and saving"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        self.other_user = User.objects.create_user(
            username="otheruser", email="other@example.com", password="testpass"
        )

    def test_form_valid_data(self):
        """Test form with valid data"""
        form = TagForm(user=self.user, data={"name": "urgent"})
        self.assertTrue(form.is_valid())

    def test_form_empty_name(self):
        """Test form with empty name"""
        form = TagForm(user=self.user, data={"name": ""})
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)
        # Django's required field validation triggers before clean_name
        self.assertIn("This field is required", str(form.errors["name"]))

    def test_form_whitespace_only_name(self):
        """Test form with whitespace-only name"""
        form = TagForm(user=self.user, data={"name": "   "})
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)

    def test_form_duplicate_name_same_user(self):
        """Test form with duplicate name for same user"""
        Tag.objects.create(name="important", user=self.user)
        form = TagForm(user=self.user, data={"name": "important"})
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)
        self.assertIn("already have a tag", str(form.errors["name"]))

    def test_form_duplicate_name_case_insensitive(self):
        """Test form with duplicate name (case-insensitive) for same user"""
        Tag.objects.create(name="important", user=self.user)
        form = TagForm(user=self.user, data={"name": "IMPORTANT"})
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)

    def test_form_duplicate_name_different_user(self):
        """Test form allows duplicate name for different users"""
        Tag.objects.create(name="important", user=self.other_user)
        form = TagForm(user=self.user, data={"name": "important"})
        self.assertTrue(form.is_valid())

    def test_form_save_assigns_user(self):
        """Test that form.save() assigns the user correctly"""
        form = TagForm(user=self.user, data={"name": "urgent"})
        self.assertTrue(form.is_valid())
        tag = form.save()
        self.assertEqual(tag.user, self.user)
        self.assertEqual(tag.name, "urgent")

    def test_form_update_allows_same_name(self):
        """Test that updating a tag allows keeping the same name"""
        tag = Tag.objects.create(name="urgent", user=self.user)
        form = TagForm(user=self.user, instance=tag, data={"name": "urgent"})
        self.assertTrue(form.is_valid())

    def test_form_update_prevents_duplicate(self):
        """Test that updating a tag prevents duplicate names"""
        Tag.objects.create(name="urgent", user=self.user)
        tag2 = Tag.objects.create(name="important", user=self.user)
        form = TagForm(user=self.user, instance=tag2, data={"name": "urgent"})
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)


class TagListViewTests(TestCase):
    """Test the TagListView"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        self.other_user = User.objects.create_user(
            username="otheruser", email="other@example.com", password="testpass"
        )

    def test_list_view_requires_login(self):
        """Test that list view requires login"""
        response = self.client.get(reverse("tag_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_list_view_returns_200(self):
        """Test that list view returns 200 for logged in user"""
        self.client.force_login(self.user)
        response = self.client.get(reverse("tag_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "tags/tag_list.html")

    def test_list_view_shows_user_tags_only(self):
        """Test that list view shows only current user's tags"""
        Tag.objects.create(name="urgent", user=self.user)
        Tag.objects.create(name="important", user=self.user)
        Tag.objects.create(name="personal", user=self.other_user)

        self.client.force_login(self.user)
        response = self.client.get(reverse("tag_list"))

        self.assertContains(response, "urgent")
        self.assertContains(response, "important")
        self.assertNotContains(response, "personal")
        self.assertEqual(len(response.context["tags"]), 2)

    def test_list_view_ordered_by_name(self):
        """Test that list view orders tags by name"""
        Tag.objects.create(name="zebra", user=self.user)
        Tag.objects.create(name="alpha", user=self.user)
        Tag.objects.create(name="middle", user=self.user)

        self.client.force_login(self.user)
        response = self.client.get(reverse("tag_list"))

        tags = response.context["tags"]
        self.assertEqual(tags[0].name, "alpha")
        self.assertEqual(tags[1].name, "middle")
        self.assertEqual(tags[2].name, "zebra")


class TagCreateViewTests(TestCase):
    """Test the TagCreateView"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )

    def test_create_view_requires_login(self):
        """Test that create view requires login"""
        response = self.client.get(reverse("tag_create"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_create_view_get_returns_200(self):
        """Test that GET request to create view returns 200"""
        self.client.force_login(self.user)
        response = self.client.get(reverse("tag_create"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "tags/tag_form.html")

    def test_create_view_post_valid_data(self):
        """Test POST with valid data creates tag"""
        self.client.force_login(self.user)
        data = {"name": "urgent"}
        response = self.client.post(reverse("tag_create"), data)
        self.assertEqual(response.status_code, 302)  # Successful creation redirects

        self.assertEqual(Tag.objects.count(), 1)
        tag = Tag.objects.first()
        self.assertEqual(tag.name, "urgent")
        self.assertEqual(tag.user, self.user)

    def test_create_view_post_shows_success_message(self):
        """Test that creating a tag shows success message"""
        self.client.force_login(self.user)
        data = {"name": "urgent"}
        response = self.client.post(reverse("tag_create"), data, follow=True)

        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertIn("created successfully", str(messages[0]))

    def test_create_view_post_invalid_data(self):
        """Test POST with invalid data shows errors"""
        self.client.force_login(self.user)
        data = {"name": ""}
        response = self.client.post(reverse("tag_create"), data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Tag.objects.count(), 0)
        self.assertContains(response, "This field is required")

    def test_create_view_prevents_duplicates(self):
        """Test that create view prevents duplicate names"""
        Tag.objects.create(name="urgent", user=self.user)
        self.client.force_login(self.user)

        data = {"name": "urgent"}
        response = self.client.post(reverse("tag_create"), data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Tag.objects.count(), 1)
        self.assertContains(response, "You already have a tag with this name")


class TagUpdateViewTests(TestCase):
    """Test the TagUpdateView"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        self.other_user = User.objects.create_user(
            username="otheruser", email="other@example.com", password="testpass"
        )
        self.tag = Tag.objects.create(name="urgent", user=self.user)

    def test_update_view_requires_login(self):
        """Test that update view requires login"""
        response = self.client.get(reverse("tag_update", args=[self.tag.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_update_view_get_returns_200(self):
        """Test that GET request to update view returns 200"""
        self.client.force_login(self.user)
        response = self.client.get(reverse("tag_update", args=[self.tag.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "tags/tag_form.html")

    def test_update_view_get_shows_current_values(self):
        """Test that update view shows current values"""
        self.client.force_login(self.user)
        response = self.client.get(reverse("tag_update", args=[self.tag.id]))
        self.assertContains(response, "urgent")

    def test_update_view_post_valid_data(self):
        """Test POST with valid data updates tag"""
        self.client.force_login(self.user)
        data = {"name": "very-urgent"}
        response = self.client.post(reverse("tag_update", args=[self.tag.id]), data)
        self.assertEqual(response.status_code, 302)  # Successful update redirects

        self.tag.refresh_from_db()
        self.assertEqual(self.tag.name, "very-urgent")

    def test_update_view_post_shows_success_message(self):
        """Test that updating a tag shows success message"""
        self.client.force_login(self.user)
        data = {"name": "urgent"}
        response = self.client.post(
            reverse("tag_update", args=[self.tag.id]), data, follow=True
        )

        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertIn("updated successfully", str(messages[0]))

    def test_update_view_user_isolation(self):
        """Test that users can only update their own tags"""
        self.client.force_login(self.other_user)
        response = self.client.get(reverse("tag_update", args=[self.tag.id]))
        self.assertEqual(response.status_code, 404)

    def test_update_view_allows_same_name(self):
        """Test that update allows keeping the same name"""
        self.client.force_login(self.user)
        data = {"name": "urgent"}
        response = self.client.post(reverse("tag_update", args=[self.tag.id]), data)
        self.assertEqual(response.status_code, 302)  # Successful update redirects

        self.tag.refresh_from_db()
        self.assertEqual(self.tag.name, "urgent")

    def test_update_view_prevents_duplicate(self):
        """Test that update prevents duplicate names"""
        tag2 = Tag.objects.create(name="important", user=self.user)
        self.client.force_login(self.user)

        data = {"name": "urgent"}
        response = self.client.post(reverse("tag_update", args=[tag2.id]), data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You already have a tag with this name")


class TagDeleteViewTests(TestCase):
    """Test the TagDeleteView"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        self.other_user = User.objects.create_user(
            username="otheruser", email="other@example.com", password="testpass"
        )
        self.tag = Tag.objects.create(name="urgent", user=self.user)

    def test_delete_view_requires_login(self):
        """Test that delete view requires login"""
        response = self.client.get(reverse("tag_delete", args=[self.tag.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_delete_view_get_returns_200(self):
        """Test that GET request to delete view returns 200"""
        self.client.force_login(self.user)
        response = self.client.get(reverse("tag_delete", args=[self.tag.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "tags/tag_confirm_delete.html")

    def test_delete_view_get_shows_tag_name(self):
        """Test that delete view shows tag name"""
        self.client.force_login(self.user)
        response = self.client.get(reverse("tag_delete", args=[self.tag.id]))
        self.assertContains(response, "urgent")

    def test_delete_view_post_deletes_tag(self):
        """Test POST deletes the tag"""
        self.client.force_login(self.user)
        response = self.client.post(reverse("tag_delete", args=[self.tag.id]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Tag.objects.count(), 0)

    def test_delete_view_post_redirects(self):
        """Test that deleting a tag redirects to list page"""
        self.client.force_login(self.user)
        response = self.client.post(reverse("tag_delete", args=[self.tag.id]))

        # Check redirect happens (messages are tested via integration tests)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Tag.objects.count(), 0)

    def test_delete_view_user_isolation(self):
        """Test that users can only delete their own tags"""
        self.client.force_login(self.other_user)
        response = self.client.get(reverse("tag_delete", args=[self.tag.id]))
        self.assertEqual(response.status_code, 404)

        response = self.client.post(reverse("tag_delete", args=[self.tag.id]))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Tag.objects.count(), 1)
