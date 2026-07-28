from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from task_processor.constants import GTDStatus
from task_processor.models import Item


class ItemDeleteViewTests(TestCase):
    """
    Delete is a hardcoded action (not an FSM transition), available on every
    item. HTMX requests get a confirm modal + in-place refresh; plain requests
    get a full-page confirm + redirect.
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="u", password="x")
        self.client.force_login(self.user)
        self.item = Item.objects.create(
            title="A reference", status=GTDStatus.REFERENCE, user=self.user
        )

    def _url(self, item=None):
        item = item or self.item
        return reverse("item_delete", kwargs={"item_id": item.pk})

    def test_htmx_get_renders_confirmation_modal(self):
        response = self.client.get(self._url(), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "items/_delete_modal.html")
        self.assertContains(response, 'id="modal"')
        self.assertContains(response, "A reference")
        # Nothing deleted on GET.
        self.assertTrue(Item.objects.filter(pk=self.item.pk).exists())

    def test_htmx_post_deletes_and_refreshes(self):
        response = self.client.post(self._url(), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Item.objects.filter(pk=self.item.pk).exists())
        self.assertEqual(response.headers.get("HX-Trigger"), "refreshItems")
        self.assertContains(response, "hx-swap-oob")

    def test_plain_get_renders_full_page_confirm(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "items/delete_confirm.html")

    def test_plain_post_deletes_and_redirects(self):
        response = self.client.post(self._url() + "?returnUrl=/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/")
        self.assertFalse(Item.objects.filter(pk=self.item.pk).exists())

    def test_delete_cascades_to_sub_items(self):
        child = Item.objects.create(
            title="Child",
            status=GTDStatus.NEXT_ACTION,
            user=self.user,
            parent=self.item,
        )
        self.client.post(self._url(), HTTP_HX_REQUEST="true")
        self.assertFalse(Item.objects.filter(pk=child.pk).exists())

    def test_cannot_delete_other_users_item(self):
        other = User.objects.create_user(username="other", password="x")
        stranger_item = Item.objects.create(
            title="Not yours", status=GTDStatus.INBOX, user=other
        )
        # GET (confirm) and POST (delete) both 404 for a non-owner.
        self.assertEqual(
            self.client.get(
                self._url(stranger_item), HTTP_HX_REQUEST="true"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                self._url(stranger_item), HTTP_HX_REQUEST="true"
            ).status_code,
            404,
        )
        self.assertTrue(Item.objects.filter(pk=stranger_item.pk).exists())

    def test_delete_action_in_item_dropdown(self):
        # The hardcoded Delete link renders for the item on the dashboard.
        response = self.client.get(f"/?q={self.item.title}")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self._url())
