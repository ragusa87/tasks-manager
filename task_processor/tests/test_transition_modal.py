from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from task_processor.constants import GTDStatus
from task_processor.models import Item


class TransitionModalViewTests(TestCase):
    """
    ItemTransitionView content-negotiates on the HX-Request header for any
    @requires_form transition (here: `delegate`, NEXT_ACTION -> WAITING_FOR).
    HTMX requests get the in-place modal partial; plain requests keep the
    full-page form. Each branch is exercised independently.
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        self.client.force_login(self.user)
        # delegate is only available from NEXT_ACTION
        self.item = Item.objects.create(
            title="Test item", status=GTDStatus.NEXT_ACTION, user=self.user
        )

    def _url(self, slug="delegate"):
        return reverse(
            "item_transition",
            kwargs={"item_id": self.item.pk, "transition_slug": slug},
        )

    # --- GET: template negotiation -----------------------------------------

    def test_htmx_get_renders_modal_partial(self):
        response = self.client.get(self._url(), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "transitions/_modal.html")
        self.assertContains(response, 'id="modal"')
        self.assertContains(response, 'name="person"')

    def test_plain_get_renders_full_page_form(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "transitions/form.html")
        self.assertContains(response, 'name="person"')

    # --- POST invalid: errors re-rendered in the modal ---------------------

    def test_htmx_post_invalid_returns_400_with_form(self):
        # WaitingForForm requires `person`; omit it to trigger validation error.
        response = self.client.post(self._url(), {}, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 400)
        self.assertTemplateUsed(response, "transitions/_modal.html")
        self.assertContains(response, 'name="person"', status_code=400)
        # Transition must NOT have been applied.
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, GTDStatus.NEXT_ACTION)

    # --- POST valid: transition applied, modal closed, list refreshed ------

    def test_htmx_post_valid_applies_transition_and_closes_modal(self):
        response = self.client.post(
            self._url(), {"person": "Alice"}, HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 200)
        # Transition applied.
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, GTDStatus.WAITING_FOR)
        self.assertEqual(self.item.waiting_for_person, "Alice")
        # Body is only the OOB flash-messages swap (no form) -> modal emptied.
        self.assertContains(response, "hx-swap-oob")
        self.assertContains(response, "flash-messages")
        self.assertNotContains(response, 'name="person"')
        # List refresh trigger.
        self.assertEqual(response.headers.get("HX-Trigger"), "refreshItems")

    def test_plain_post_valid_redirects(self):
        response = self.client.post(self._url() + "?returnUrl=/", {"person": "Bob"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/")
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, GTDStatus.WAITING_FOR)

    # --- Formless transition still executes immediately + redirects --------

    def test_formless_transition_redirects_even_with_htmx(self):
        # `complete` has no form: dispatch executes it and redirects regardless.
        response = self.client.get(self._url("complete"), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, GTDStatus.COMPLETED)

    def test_transition_requires_ownership(self):
        other = User.objects.create_user(username="other", password="x")
        self.client.force_login(other)
        response = self.client.get(self._url(), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 404)


class ReferenceConversionModalTests(TestCase):
    """
    Converting an item to a Reference opens the modal with a parent picker
    (ReferenceForm). Works from INBOX (process_as_reference) and NEXT_ACTION
    (convert_as_reference).
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="ref", password="x")
        self.client.force_login(self.user)
        self.item = Item.objects.create(
            title="Inbox item", status=GTDStatus.INBOX, user=self.user
        )
        # A valid parent (project) and an invalid one (plain next action).
        self.project = Item.objects.create(
            title="A project", status=GTDStatus.PROJECT, user=self.user
        )
        self.next_action = Item.objects.create(
            title="Some action", status=GTDStatus.NEXT_ACTION, user=self.user
        )
        self.other_project = Item.objects.create(
            title="Other user project",
            status=GTDStatus.PROJECT,
            user=User.objects.create_user(username="stranger", password="x"),
        )

    def _url(self, item=None, slug="process_as_reference"):
        item = item or self.item
        return reverse(
            "item_transition",
            kwargs={"item_id": item.pk, "transition_slug": slug},
        )

    def test_reference_transition_shows_parent_picker(self):
        response = self.client.get(self._url(), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "transitions/_modal.html")
        # Searchable autocomplete widget (options come from the AJAX endpoint,
        # not rendered inline), backed by the hidden `parent` input.
        self.assertContains(response, "autocomplete-container")
        self.assertContains(response, 'data-field-type="parent"')
        self.assertContains(response, 'name="parent"')

    def test_wrong_type_parent_is_rejected(self):
        # A Reference may only be filed under a Project or another Reference.
        # A Next Action id must fail validation (400) and not convert.
        response = self.client.post(
            self._url(), {"parent": self.next_action.pk}, HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 400)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, GTDStatus.INBOX)
        self.assertIsNone(self.item.parent)

    def test_parent_autocomplete_endpoint_source(self):
        # The picker's data source: user's top-level projects/references only.
        url = reverse("autocomplete", args=["parent"])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        texts = [r["text"] for r in response.json()["results"]]
        self.assertIn("A project (Project)", texts)
        self.assertNotIn("Other user project (Project)", texts)
        self.assertNotIn("Inbox item (Inbox)", texts)

    def test_convert_with_parent(self):
        response = self.client.post(
            self._url(), {"parent": self.project.pk}, HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, GTDStatus.REFERENCE)
        self.assertEqual(self.item.parent, self.project)

    def test_convert_without_parent(self):
        response = self.client.post(self._url(), {}, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, GTDStatus.REFERENCE)
        self.assertIsNone(self.item.parent)

    def test_convert_from_next_action(self):
        response = self.client.post(
            self._url(item=self.next_action, slug="convert_as_reference"),
            {"parent": self.project.pk},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.next_action.refresh_from_db()
        self.assertEqual(self.next_action.status, GTDStatus.REFERENCE)
        self.assertEqual(self.next_action.parent, self.project)
