from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from task_processor.constants import GTDStatus, Priority
from task_processor.models import Area, Context, Document, Item, Tag


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

    def test_dashboard_pagination_preserves_search_query(self):
        """Pagination links must keep q (and any other params), not reset them."""
        self.client.force_login(self.user)
        for i in range(51):  # one over paginate_by=50
            Item.objects.create(title=f"paginated {i}", user=self.user)

        response = self.client.get("/?q=paginated")
        self.assertContains(response, "?q=paginated&amp;page=2")

        response = self.client.get("/?q=paginated&page=2")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "?q=paginated&amp;page=1")

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


class TestDashboardStatsView(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="stats", password="testpass")
        self.other = User.objects.create_user(username="other", password="testpass")

    def test_status_stats_counts_per_status_in_declaration_order(self):
        for _ in range(2):
            Item.objects.create(title="i", user=self.user, status=GTDStatus.INBOX)
        Item.objects.create(title="n", user=self.user, status=GTDStatus.NEXT_ACTION)
        Item.objects.create(title="x", user=self.other, status=GTDStatus.INBOX)

        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard_stats"))

        stats = response.context["status_stats"]
        self.assertEqual([s["value"] for s in stats], list(GTDStatus.values))
        counts = {s["value"]: s["count"] for s in stats}
        self.assertEqual(counts[GTDStatus.INBOX], 2)  # other user's item excluded
        self.assertEqual(counts[GTDStatus.NEXT_ACTION], 1)
        self.assertEqual(counts[GTDStatus.COMPLETED], 0)  # zero counts included

    def test_status_stats_entries_carry_label_and_sprite(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard_stats"))
        by_value = {s["value"]: s for s in response.context["status_stats"]}
        self.assertEqual(by_value[GTDStatus.INBOX]["label"], "Inbox")
        self.assertEqual(by_value[GTDStatus.INBOX]["sprite"], "lucide-inbox")
        # Serialized into the page for charts.js via json_script
        self.assertContains(response, 'id="status-stats-data"')

    def test_requires_authentication(self):
        response = self.client.get(reverse("dashboard_stats"))
        self.assertEqual(response.status_code, 302)

    def _create_document(self, user, item, name, size, content_type):
        return Document.objects.create(
            item=item,
            file_name=name,
            file_size=size,
            content_type=content_type,
            content_hash=name,  # unique per (item, hash); no real file needed
            user=user,
        )

    def test_disk_stats_sums_sizes_per_content_family(self):
        item = Item.objects.create(title="i", user=self.user)
        self._create_document(self.user, item, "a.png", 1000, "image/png")
        self._create_document(self.user, item, "b.jpg", 500, "image/jpeg")
        self._create_document(self.user, item, "c.ogg", 200, "audio/ogg")
        self._create_document(self.user, item, "d.pdf", 30, "application/pdf")
        foreign_item = Item.objects.create(title="f", user=self.other)
        self._create_document(self.other, foreign_item, "e.png", 9999, "image/png")

        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard_stats"))

        disk = response.context["disk_stats"]
        self.assertEqual(disk["total_size"], 1730)  # other user's file excluded
        self.assertEqual(disk["total_count"], 4)
        by_value = {c["value"]: c for c in disk["categories"]}
        self.assertEqual(by_value["images"]["size"], 1500)
        self.assertEqual(by_value["images"]["count"], 2)
        self.assertEqual(by_value["audio"]["size"], 200)
        self.assertEqual(by_value["other"]["size"], 30)
        # Serialized into the page for charts.js via json_script
        self.assertContains(response, 'id="disk-stats-data"')

    def test_disk_stats_empty_without_documents(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard_stats"))
        disk = response.context["disk_stats"]
        self.assertEqual(disk["total_size"], 0)
        self.assertEqual(disk["total_count"], 0)
        self.assertEqual([c["size"] for c in disk["categories"]], [0, 0, 0])


class TestItemDetailViewTemplates(TestCase):
    """The detail URL serves the modal partial to HTMX and a full page to
    plain requests (deep link / refresh on the history-pushed URL)."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        self.client.force_login(self.user)
        self.item = Item.objects.create(
            title="Deep-linked item",
            status=GTDStatus.NEXT_ACTION,
            priority=Priority.NORMAL,
            user=self.user,
        )
        self.url = reverse("item_detail", kwargs={"item_id": self.item.pk})

    def test_htmx_get_renders_modal_partial(self):
        response = self.client.get(self.url, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "partials/item_detail_modal.html")
        self.assertContains(response, 'id="modal"')

    def test_plain_get_renders_full_page(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "items/detail.html")
        self.assertTemplateUsed(response, "base.html")
        self.assertContains(response, "Deep-linked item")
        # base.html ships an empty #modal placeholder; the page itself must
        # not render the modal dialog variant of the form.
        self.assertNotContains(response, "aria-modal")

    def test_plain_post_saves_and_redirects(self):
        response = self.client.post(
            self.url,
            {
                "title": "Renamed item",
                "priority": self.item.priority,
                "parent": "",
                "rrule": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.url)
        self.item.refresh_from_db()
        self.assertEqual(self.item.title, "Renamed item")

    def test_plain_post_invalid_rerenders_full_page(self):
        response = self.client.post(
            self.url,
            {"title": "", "priority": self.item.priority, "parent": "", "rrule": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "items/detail.html")

    def test_other_users_item_is_404(self):
        other = User.objects.create_user(username="other", password="x")
        other_item = Item.objects.create(
            title="Not yours", status=GTDStatus.INBOX, user=other
        )
        response = self.client.get(
            reverse("item_detail", kwargs={"item_id": other_item.pk})
        )
        self.assertEqual(response.status_code, 404)


class TestItemOffloadView(TestCase):
    """Test the standalone quick-capture page"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )

    def test_requires_authentication(self):
        response = self.client.get(reverse("item_offload"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_renders_for_logged_in_user(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("item_offload"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "items/offload.html")

    def test_page_provides_csrf_token_for_the_api_calls(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("item_offload"))
        self.assertContains(response, "csrfmiddlewaretoken")

    def test_app_nav_links_to_the_offload_page(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, reverse("item_offload"))

    def test_page_is_installable_on_mobile(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("item_offload"))
        self.assertContains(response, "offload.webmanifest")
        self.assertContains(response, "apple-mobile-web-app-capable")
        self.assertContains(response, "apple-touch-icon")


class TestLogoutView(TestCase):
    """Test the logout view clears every session layer"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )

    def test_logout_redirects_to_logout_redirect_url(self):
        """Logout redirects to LOGOUT_REDIRECT_URL (Keycloak end-session in prod)"""
        self.client.force_login(self.user)
        with self.settings(
            LOGOUT_REDIRECT_URL="https://keycloak.example.com/realms/x/protocol/openid-connect/logout"
        ):
            response = self.client.get(reverse("logout"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            "https://keycloak.example.com/realms/x/protocol/openid-connect/logout",
        )

    def test_logout_clears_django_session(self):
        """Logout de-authenticates the Django session"""
        self.client.force_login(self.user)
        self.client.get(reverse("logout"))
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_logout_deletes_auth_proxy_cookie(self):
        """Logout expires the auth proxy (traefik keycloakopenid) cookie"""
        self.client.force_login(self.user)
        self.client.cookies["AUTH_TOKEN"] = "some-jwt"
        response = self.client.get(reverse("logout"))
        cookie = response.cookies["AUTH_TOKEN"]
        self.assertEqual(cookie.value, "")
        self.assertEqual(cookie["max-age"], 0)

    @staticmethod
    def _jwt(payload):
        import base64
        import json

        body = (
            base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
        )
        return f"header.{body}.sig"

    def test_logout_derives_url_from_jwt_when_enabled(self):
        """With AUTH_PROXY_LOGOUT_FROM_JWT and the trusted proxy header, logout
        redirects to the token's Keycloak end-session endpoint instead of
        LOGOUT_REDIRECT_URL"""
        self.client.force_login(self.user)
        self.client.cookies["AUTH_TOKEN"] = self._jwt(
            {"iss": "https://keycloak.example.com/realms/example", "azp": "tasks"}
        )
        with self.settings(
            AUTH_PROXY_LOGOUT_FROM_JWT=True, LOGOUT_REDIRECT_URL="/login/"
        ):
            response = self.client.get(
                reverse("logout"), HTTP_X_TOKEN_USER_NAME="alice"
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            "https://keycloak.example.com/realms/example"
            "/protocol/openid-connect/logout?client_id=tasks",
        )

    def test_logout_ignores_jwt_without_trusted_header(self):
        """A valid JWT cookie must NOT drive the logout redirect unless the
        trusted proxy header gates the request — otherwise a forged cookie
        (e.g. cookie injection, or the app reached directly) could redirect
        logout to an attacker-chosen issuer."""
        self.client.force_login(self.user)
        self.client.cookies["AUTH_TOKEN"] = self._jwt(
            {"iss": "https://evil.example.com/realms/example", "azp": "tasks"}
        )
        with self.settings(
            AUTH_PROXY_LOGOUT_FROM_JWT=True, LOGOUT_REDIRECT_URL="/login/"
        ):
            response = self.client.get(reverse("logout"))  # no proxy header
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/login/")
        self.assertNotIn("evil.example.com", response.url)

    def test_logout_falls_back_to_configured_url_without_jwt(self):
        """When the cookie is not a decodable JWT, logout uses LOGOUT_REDIRECT_URL"""
        self.client.force_login(self.user)
        self.client.cookies["AUTH_TOKEN"] = "opaque-not-a-jwt"
        with self.settings(
            AUTH_PROXY_LOGOUT_FROM_JWT=True, LOGOUT_REDIRECT_URL="/login/"
        ):
            response = self.client.get(
                reverse("logout"), HTTP_X_TOKEN_USER_NAME="alice"
            )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_logout_when_anonymous_still_redirects(self):
        """Logout works without an authenticated user"""
        response = self.client.get(reverse("logout"))
        self.assertEqual(response.status_code, 302)
