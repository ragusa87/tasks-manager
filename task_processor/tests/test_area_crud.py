from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from task_processor.forms import AreaForm
from task_processor.models import Area


class AreaFormTests(TestCase):
    """Test the AreaForm validation and saving"""

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
        form = AreaForm(
            user=self.user,
            data={"name": "Health", "description": "Health and fitness goals"},
        )
        self.assertTrue(form.is_valid())

    def test_form_empty_name(self):
        """Test form with empty name"""
        form = AreaForm(user=self.user, data={"name": "", "description": "Test"})
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)
        # Django's required field validation triggers before clean_name
        self.assertIn("This field is required", str(form.errors["name"]))

    def test_form_whitespace_only_name(self):
        """Test form with whitespace-only name"""
        form = AreaForm(user=self.user, data={"name": "   ", "description": "Test"})
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)

    def test_form_duplicate_name_same_user(self):
        """Test form with duplicate name for same user"""
        Area.objects.create(name="Finance", user=self.user)
        form = AreaForm(
            user=self.user, data={"name": "Finance", "description": "New finance area"}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)
        self.assertIn("already have an area", str(form.errors["name"]))

    def test_form_duplicate_name_case_insensitive(self):
        """Test form with duplicate name (case-insensitive) for same user"""
        Area.objects.create(name="Finance", user=self.user)
        form = AreaForm(
            user=self.user, data={"name": "FINANCE", "description": "New finance area"}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)

    def test_form_duplicate_name_different_user(self):
        """Test form allows duplicate name for different users"""
        Area.objects.create(name="Finance", user=self.other_user)
        form = AreaForm(
            user=self.user, data={"name": "Finance", "description": "My finance area"}
        )
        self.assertTrue(form.is_valid())

    def test_form_save_assigns_user(self):
        """Test that form.save() assigns the user correctly"""
        form = AreaForm(
            user=self.user,
            data={"name": "Career", "description": "Career development"},
        )
        self.assertTrue(form.is_valid())
        area = form.save()
        self.assertEqual(area.user, self.user)
        self.assertEqual(area.name, "Career")
        self.assertEqual(area.description, "Career development")

    def test_form_update_allows_same_name(self):
        """Test that updating an area allows keeping the same name"""
        area = Area.objects.create(name="Health", user=self.user)
        form = AreaForm(
            user=self.user,
            instance=area,
            data={"name": "Health", "description": "Updated description"},
        )
        self.assertTrue(form.is_valid())

    def test_form_update_prevents_duplicate(self):
        """Test that updating an area prevents duplicate names"""
        Area.objects.create(name="Health", user=self.user)
        area2 = Area.objects.create(name="Finance", user=self.user)
        form = AreaForm(
            user=self.user, instance=area2, data={"name": "Health", "description": ""}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)


class AreaListViewTests(TestCase):
    """Test the AreaListView"""

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
        response = self.client.get(reverse("area_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_list_view_returns_200(self):
        """Test that list view returns 200 for logged in user"""
        self.client.force_login(self.user)
        response = self.client.get(reverse("area_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "areas/area_list.html")

    def test_list_view_shows_user_areas_only(self):
        """Test that list view shows only current user's areas"""
        Area.objects.create(name="Health", user=self.user)
        Area.objects.create(name="Finance", user=self.user)
        Area.objects.create(name="Career", user=self.other_user)

        self.client.force_login(self.user)
        response = self.client.get(reverse("area_list"))

        self.assertContains(response, "Health")
        self.assertContains(response, "Finance")
        self.assertNotContains(response, "Career")
        self.assertEqual(len(response.context["areas"]), 2)

    def test_list_view_ordered_by_name(self):
        """Test that list view orders areas by name"""
        Area.objects.create(name="Zebra", user=self.user)
        Area.objects.create(name="Alpha", user=self.user)
        Area.objects.create(name="Middle", user=self.user)

        self.client.force_login(self.user)
        response = self.client.get(reverse("area_list"))

        areas = response.context["areas"]
        self.assertEqual(areas[0].name, "Alpha")
        self.assertEqual(areas[1].name, "Middle")
        self.assertEqual(areas[2].name, "Zebra")


class AreaCreateViewTests(TestCase):
    """Test the AreaCreateView"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )

    def test_create_view_requires_login(self):
        """Test that create view requires login"""
        response = self.client.get(reverse("area_create"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_create_view_get_returns_200(self):
        """Test that GET request to create view returns 200"""
        self.client.force_login(self.user)
        response = self.client.get(reverse("area_create"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "areas/area_form.html")

    def test_create_view_post_valid_data(self):
        """Test POST with valid data creates area"""
        self.client.force_login(self.user)
        data = {"name": "Health", "description": "Health and fitness"}
        response = self.client.post(reverse("area_create"), data)
        self.assertEqual(response.status_code, 302)  # Successful creation redirects

        self.assertEqual(Area.objects.count(), 1)
        area = Area.objects.first()
        self.assertEqual(area.name, "Health")
        self.assertEqual(area.description, "Health and fitness")
        self.assertEqual(area.user, self.user)

    def test_create_view_post_shows_success_message(self):
        """Test that creating an area shows success message"""
        self.client.force_login(self.user)
        data = {"name": "Health", "description": ""}
        response = self.client.post(reverse("area_create"), data, follow=True)

        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertIn("created successfully", str(messages[0]))

    def test_create_view_post_invalid_data(self):
        """Test POST with invalid data shows errors"""
        self.client.force_login(self.user)
        data = {"name": "", "description": ""}
        response = self.client.post(reverse("area_create"), data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Area.objects.count(), 0)
        self.assertContains(response, "This field is required")

    def test_create_view_prevents_duplicates(self):
        """Test that create view prevents duplicate names"""
        Area.objects.create(name="Health", user=self.user)
        self.client.force_login(self.user)

        data = {"name": "Health", "description": "Duplicate"}
        response = self.client.post(reverse("area_create"), data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Area.objects.count(), 1)
        self.assertContains(response, "You already have an area with this name")


class AreaUpdateViewTests(TestCase):
    """Test the AreaUpdateView"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        self.other_user = User.objects.create_user(
            username="otheruser", email="other@example.com", password="testpass"
        )
        self.area = Area.objects.create(
            name="Health", description="Original description", user=self.user
        )

    def test_update_view_requires_login(self):
        """Test that update view requires login"""
        response = self.client.get(reverse("area_update", args=[self.area.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_update_view_get_returns_200(self):
        """Test that GET request to update view returns 200"""
        self.client.force_login(self.user)
        response = self.client.get(reverse("area_update", args=[self.area.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "areas/area_form.html")

    def test_update_view_get_shows_current_values(self):
        """Test that update view shows current values"""
        self.client.force_login(self.user)
        response = self.client.get(reverse("area_update", args=[self.area.id]))
        self.assertContains(response, "Health")
        self.assertContains(response, "Original description")

    def test_update_view_post_valid_data(self):
        """Test POST with valid data updates area"""
        self.client.force_login(self.user)
        data = {"name": "Updated Health", "description": "Updated description"}
        response = self.client.post(reverse("area_update", args=[self.area.id]), data)
        self.assertEqual(response.status_code, 302)  # Successful update redirects

        self.area.refresh_from_db()
        self.assertEqual(self.area.name, "Updated Health")
        self.assertEqual(self.area.description, "Updated description")

    def test_update_view_post_shows_success_message(self):
        """Test that updating an area shows success message"""
        self.client.force_login(self.user)
        data = {"name": "Health", "description": "Updated"}
        response = self.client.post(
            reverse("area_update", args=[self.area.id]), data, follow=True
        )

        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertIn("updated successfully", str(messages[0]))

    def test_update_view_user_isolation(self):
        """Test that users can only update their own areas"""
        self.client.force_login(self.other_user)
        response = self.client.get(reverse("area_update", args=[self.area.id]))
        self.assertEqual(response.status_code, 404)

    def test_update_view_allows_same_name(self):
        """Test that update allows keeping the same name"""
        self.client.force_login(self.user)
        data = {"name": "Health", "description": "New description"}
        response = self.client.post(reverse("area_update", args=[self.area.id]), data)
        self.assertEqual(response.status_code, 302)  # Successful update redirects

        self.area.refresh_from_db()
        self.assertEqual(self.area.description, "New description")

    def test_update_view_prevents_duplicate(self):
        """Test that update prevents duplicate names"""
        area2 = Area.objects.create(name="Finance", user=self.user)
        self.client.force_login(self.user)

        data = {"name": "Health", "description": ""}
        response = self.client.post(reverse("area_update", args=[area2.id]), data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You already have an area with this name")


class AreaDeleteViewTests(TestCase):
    """Test the AreaDeleteView"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        self.other_user = User.objects.create_user(
            username="otheruser", email="other@example.com", password="testpass"
        )
        self.area = Area.objects.create(name="Health", user=self.user)

    def test_delete_view_requires_login(self):
        """Test that delete view requires login"""
        response = self.client.get(reverse("area_delete", args=[self.area.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_delete_view_get_returns_200(self):
        """Test that GET request to delete view returns 200"""
        self.client.force_login(self.user)
        response = self.client.get(reverse("area_delete", args=[self.area.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "areas/area_confirm_delete.html")

    def test_delete_view_get_shows_area_name(self):
        """Test that delete view shows area name"""
        self.client.force_login(self.user)
        response = self.client.get(reverse("area_delete", args=[self.area.id]))
        self.assertContains(response, "Health")

    def test_delete_view_post_deletes_area(self):
        """Test POST deletes the area"""
        self.client.force_login(self.user)
        response = self.client.post(reverse("area_delete", args=[self.area.id]))
        self.assertEqual(response.status_code, 302)  # Successful deletion redirects

        self.assertEqual(Area.objects.count(), 0)

    def test_delete_view_post_redirects(self):
        """Test that deleting an area redirects to list page"""
        self.client.force_login(self.user)
        response = self.client.post(reverse("area_delete", args=[self.area.id]))

        # Check redirect happens (messages are tested via integration tests)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Area.objects.count(), 0)

    def test_delete_view_user_isolation(self):
        """Test that users can only delete their own areas"""
        self.client.force_login(self.other_user)
        response = self.client.get(reverse("area_delete", args=[self.area.id]))
        self.assertEqual(response.status_code, 404)

        response = self.client.post(reverse("area_delete", args=[self.area.id]))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Area.objects.count(), 1)
