from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from task_processor.forms import ContextForm
from task_processor.models import Context


class ContextFormTests(TestCase):
    """Test the ContextForm validation and saving"""

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
        form = ContextForm(
            user=self.user,
            data={"name": "@home", "description": "Tasks to do at home"},
        )
        self.assertTrue(form.is_valid())

    def test_form_empty_name(self):
        """Test form with empty name"""
        form = ContextForm(user=self.user, data={"name": "", "description": "Test"})
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)
        # Django's required field validation triggers before clean_name
        self.assertIn("This field is required", str(form.errors["name"]))

    def test_form_whitespace_only_name(self):
        """Test form with whitespace-only name"""
        form = ContextForm(user=self.user, data={"name": "   ", "description": "Test"})
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)

    def test_form_duplicate_name_same_user(self):
        """Test form with duplicate name for same user"""
        Context.objects.create(name="@office", user=self.user)
        form = ContextForm(
            user=self.user,
            data={"name": "@office", "description": "New office context"},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)
        self.assertIn("already have a context", str(form.errors["name"]))

    def test_form_duplicate_name_case_insensitive(self):
        """Test form with duplicate name (case-insensitive) for same user"""
        Context.objects.create(name="@office", user=self.user)
        form = ContextForm(
            user=self.user,
            data={"name": "@OFFICE", "description": "New office context"},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)

    def test_form_duplicate_name_different_user(self):
        """Test form allows duplicate name for different users"""
        Context.objects.create(name="@office", user=self.other_user)
        form = ContextForm(
            user=self.user, data={"name": "@office", "description": "My office context"}
        )
        self.assertTrue(form.is_valid())

    def test_form_save_assigns_user(self):
        """Test that form.save() assigns the user correctly"""
        form = ContextForm(
            user=self.user,
            data={"name": "@home", "description": "Home tasks"},
        )
        self.assertTrue(form.is_valid())
        context = form.save()
        self.assertEqual(context.user, self.user)
        self.assertEqual(context.name, "@home")
        self.assertEqual(context.description, "Home tasks")

    def test_form_update_allows_same_name(self):
        """Test that updating a context allows keeping the same name"""
        context = Context.objects.create(name="@home", user=self.user)
        form = ContextForm(
            user=self.user,
            instance=context,
            data={"name": "@home", "description": "Updated description"},
        )
        self.assertTrue(form.is_valid())

    def test_form_update_prevents_duplicate(self):
        """Test that updating a context prevents duplicate names"""
        Context.objects.create(name="@home", user=self.user)
        context2 = Context.objects.create(name="@office", user=self.user)
        form = ContextForm(
            user=self.user,
            instance=context2,
            data={"name": "@home", "description": ""},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)


class ContextListViewTests(TestCase):
    """Test the ContextListView"""

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
        response = self.client.get(reverse("context_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_list_view_returns_200(self):
        """Test that list view returns 200 for logged in user"""
        self.client.force_login(self.user)
        response = self.client.get(reverse("context_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "contexts/context_list.html")

    def test_list_view_shows_user_contexts_only(self):
        """Test that list view shows only current user's contexts"""
        Context.objects.create(name="@home", user=self.user)
        Context.objects.create(name="@office", user=self.user)
        Context.objects.create(name="@phone", user=self.other_user)

        self.client.force_login(self.user)
        response = self.client.get(reverse("context_list"))

        self.assertContains(response, "@home")
        self.assertContains(response, "@office")
        self.assertNotContains(response, "@phone")
        self.assertEqual(len(response.context["contexts"]), 2)

    def test_list_view_ordered_by_name(self):
        """Test that list view orders contexts by name"""
        Context.objects.create(name="@zebra", user=self.user)
        Context.objects.create(name="@alpha", user=self.user)
        Context.objects.create(name="@middle", user=self.user)

        self.client.force_login(self.user)
        response = self.client.get(reverse("context_list"))

        contexts = response.context["contexts"]
        self.assertEqual(contexts[0].name, "@alpha")
        self.assertEqual(contexts[1].name, "@middle")
        self.assertEqual(contexts[2].name, "@zebra")


class ContextCreateViewTests(TestCase):
    """Test the ContextCreateView"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )

    def test_create_view_requires_login(self):
        """Test that create view requires login"""
        response = self.client.get(reverse("context_create"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_create_view_get_returns_200(self):
        """Test that GET request to create view returns 200"""
        self.client.force_login(self.user)
        response = self.client.get(reverse("context_create"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "contexts/context_form.html")

    def test_create_view_post_valid_data(self):
        """Test POST with valid data creates context"""
        self.client.force_login(self.user)
        data = {"name": "@home", "description": "Tasks at home"}
        response = self.client.post(reverse("context_create"), data)
        self.assertEqual(response.status_code, 302)  # Successful creation redirects

        self.assertEqual(Context.objects.count(), 1)
        context = Context.objects.first()
        self.assertEqual(context.name, "@home")
        self.assertEqual(context.description, "Tasks at home")
        self.assertEqual(context.user, self.user)

    def test_create_view_post_shows_success_message(self):
        """Test that creating a context shows success message"""
        self.client.force_login(self.user)
        data = {"name": "@home", "description": ""}
        response = self.client.post(reverse("context_create"), data, follow=True)

        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertIn("created successfully", str(messages[0]))

    def test_create_view_post_invalid_data(self):
        """Test POST with invalid data shows errors"""
        self.client.force_login(self.user)
        data = {"name": "", "description": ""}
        response = self.client.post(reverse("context_create"), data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Context.objects.count(), 0)
        self.assertContains(response, "This field is required")

    def test_create_view_prevents_duplicates(self):
        """Test that create view prevents duplicate names"""
        Context.objects.create(name="@home", user=self.user)
        self.client.force_login(self.user)

        data = {"name": "@home", "description": "Duplicate"}
        response = self.client.post(reverse("context_create"), data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Context.objects.count(), 1)
        self.assertContains(response, "You already have a context with this name")


class ContextUpdateViewTests(TestCase):
    """Test the ContextUpdateView"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        self.other_user = User.objects.create_user(
            username="otheruser", email="other@example.com", password="testpass"
        )
        self.context = Context.objects.create(
            name="@home", description="Original description", user=self.user
        )

    def test_update_view_requires_login(self):
        """Test that update view requires login"""
        response = self.client.get(reverse("context_update", args=[self.context.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_update_view_get_returns_200(self):
        """Test that GET request to update view returns 200"""
        self.client.force_login(self.user)
        response = self.client.get(reverse("context_update", args=[self.context.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "contexts/context_form.html")

    def test_update_view_get_shows_current_values(self):
        """Test that update view shows current values"""
        self.client.force_login(self.user)
        response = self.client.get(reverse("context_update", args=[self.context.id]))
        self.assertContains(response, "@home")
        self.assertContains(response, "Original description")

    def test_update_view_post_valid_data(self):
        """Test POST with valid data updates context"""
        self.client.force_login(self.user)
        data = {"name": "@home-updated", "description": "Updated description"}
        response = self.client.post(
            reverse("context_update", args=[self.context.id]), data
        )
        self.assertEqual(response.status_code, 302)  # Successful update redirects

        self.context.refresh_from_db()
        self.assertEqual(self.context.name, "@home-updated")
        self.assertEqual(self.context.description, "Updated description")

    def test_update_view_post_shows_success_message(self):
        """Test that updating a context shows success message"""
        self.client.force_login(self.user)
        data = {"name": "@home", "description": "Updated"}
        response = self.client.post(
            reverse("context_update", args=[self.context.id]), data, follow=True
        )

        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertIn("updated successfully", str(messages[0]))

    def test_update_view_user_isolation(self):
        """Test that users can only update their own contexts"""
        self.client.force_login(self.other_user)
        response = self.client.get(reverse("context_update", args=[self.context.id]))
        self.assertEqual(response.status_code, 404)

    def test_update_view_allows_same_name(self):
        """Test that update allows keeping the same name"""
        self.client.force_login(self.user)
        data = {"name": "@home", "description": "New description"}
        response = self.client.post(
            reverse("context_update", args=[self.context.id]), data
        )
        self.assertEqual(response.status_code, 302)  # Successful update redirects

        self.context.refresh_from_db()
        self.assertEqual(self.context.description, "New description")

    def test_update_view_prevents_duplicate(self):
        """Test that update prevents duplicate names"""
        context2 = Context.objects.create(name="@office", user=self.user)
        self.client.force_login(self.user)

        data = {"name": "@home", "description": ""}
        response = self.client.post(reverse("context_update", args=[context2.id]), data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You already have a context with this name")


class ContextDeleteViewTests(TestCase):
    """Test the ContextDeleteView"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        self.other_user = User.objects.create_user(
            username="otheruser", email="other@example.com", password="testpass"
        )
        self.context = Context.objects.create(name="@home", user=self.user)

    def test_delete_view_requires_login(self):
        """Test that delete view requires login"""
        response = self.client.get(reverse("context_delete", args=[self.context.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_delete_view_get_returns_200(self):
        """Test that GET request to delete view returns 200"""
        self.client.force_login(self.user)
        response = self.client.get(reverse("context_delete", args=[self.context.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "contexts/context_confirm_delete.html")

    def test_delete_view_get_shows_context_name(self):
        """Test that delete view shows context name"""
        self.client.force_login(self.user)
        response = self.client.get(reverse("context_delete", args=[self.context.id]))
        self.assertContains(response, "@home")

    def test_delete_view_post_deletes_context(self):
        """Test POST deletes the context"""
        self.client.force_login(self.user)
        response = self.client.post(reverse("context_delete", args=[self.context.id]))
        self.assertEqual(response.status_code, 302)  # Successful deletion redirects

        self.assertEqual(Context.objects.count(), 0)

    def test_delete_view_post_redirects(self):
        """Test that deleting a context redirects to list page"""
        self.client.force_login(self.user)
        response = self.client.post(reverse("context_delete", args=[self.context.id]))

        # Check redirect happens (messages are tested via integration tests)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Context.objects.count(), 0)

    def test_delete_view_user_isolation(self):
        """Test that users can only delete their own contexts"""
        self.client.force_login(self.other_user)
        response = self.client.get(reverse("context_delete", args=[self.context.id]))
        self.assertEqual(response.status_code, 404)

        response = self.client.post(reverse("context_delete", args=[self.context.id]))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Context.objects.count(), 1)
