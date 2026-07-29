"""Parent selection on ItemForm when the stored parent left the allowed set.

Completing a project rewrites its status to COMPLETED while its children keep
pointing at it. The existing parent is grandfathered — the item must stay
saveable with it (or with the parent cleared) — but a *newly chosen* parent
still has to be a project/reference.
"""

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from task_processor.constants import GTDStatus
from task_processor.forms import ItemForm
from task_processor.models import Item


class ItemFormCompletedParentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u", password="x")
        self.project = Item.objects.create(
            title="Old project", status=GTDStatus.PROJECT, user=self.user
        )
        self.child = Item.objects.create(
            title="Child task",
            status=GTDStatus.NEXT_ACTION,
            user=self.user,
            parent=self.project,
        )
        # Completing the project moves it out of STATUS_WITH_PARENT_ALLOWED.
        self.project.flow.complete()
        self.project.refresh_from_db()
        assert self.project.status == GTDStatus.COMPLETED

    def _form(self, **overrides):
        data = {
            "title": self.child.title,
            "priority": self.child.priority,
            "parent": str(self.project.pk),
            "rrule": "",
        }
        data.update(overrides)
        return ItemForm(
            data=data,
            instance=self.child,
            item_flow=self.child.flow,
            user=self.user,
        )

    def test_completed_parent_is_still_a_choice(self):
        form = ItemForm(instance=self.child, item_flow=self.child.flow, user=self.user)
        self.assertIn(
            self.project.pk,
            form.fields["parent"].queryset.values_list("pk", flat=True),
        )

    def test_saving_with_unchanged_completed_parent_is_valid(self):
        form = self._form()
        self.assertTrue(form.is_valid(), form.errors)
        item = form.save()
        self.assertEqual(item.parent_id, self.project.pk)

    def test_clearing_the_parent_is_valid(self):
        form = self._form(parent="")
        self.assertTrue(form.is_valid(), form.errors)
        item = form.save()
        self.assertIsNone(item.parent_id)

    def test_choosing_another_completed_item_as_parent_is_rejected(self):
        other_done = Item.objects.create(
            title="Another project", status=GTDStatus.PROJECT, user=self.user
        )
        other_done.flow.complete()
        other_done.refresh_from_db()

        form = self._form(parent=str(other_done.pk))
        self.assertFalse(form.is_valid())
        self.assertIn("parent", form.errors)

    def test_model_clean_grandfathers_unchanged_parent(self):
        # full_clean is what the form triggers via _post_clean.
        self.child.full_clean()

    def test_model_clean_rejects_new_completed_parent(self):
        sibling = Item.objects.create(
            title="Sibling", status=GTDStatus.NEXT_ACTION, user=self.user
        )
        sibling.parent = self.project
        with self.assertRaises(ValidationError):
            sibling.full_clean()


class ItemFormParentChoicesTests(TestCase):
    """The parent choices must accept everything the autocomplete dropdown
    offers: the user's top-level projects AND references (the endpoint
    filters on STATUS_WITH_PARENT_ALLOWED). Regression: the form restricted
    the queryset to a single status, so picking a reference from the
    dropdown always failed 'Select a valid choice'."""

    def setUp(self):
        self.user = User.objects.create_user(username="u", password="x")
        self.action = Item.objects.create(
            title="An action", status=GTDStatus.NEXT_ACTION, user=self.user
        )
        self.project = Item.objects.create(
            title="A project", status=GTDStatus.PROJECT, user=self.user
        )
        self.reference = Item.objects.create(
            title="A reference", status=GTDStatus.REFERENCE, user=self.user
        )

    def _form(self, instance, data=None):
        return ItemForm(
            data=data, instance=instance, item_flow=instance.flow, user=self.user
        )

    def test_choices_include_projects_and_references(self):
        ids = set(
            self._form(self.action)
            .fields["parent"]
            .queryset.values_list("pk", flat=True)
        )
        self.assertIn(self.project.pk, ids)
        self.assertIn(self.reference.pk, ids)

    def test_item_cannot_be_its_own_parent_choice(self):
        ids = set(
            self._form(self.reference)
            .fields["parent"]
            .queryset.values_list("pk", flat=True)
        )
        self.assertNotIn(self.reference.pk, ids)
        self.assertIn(self.project.pk, ids)

    def test_action_can_be_filed_under_a_reference(self):
        form = self._form(
            self.action,
            data={
                "title": self.action.title,
                "priority": self.action.priority,
                "parent": str(self.reference.pk),
                "rrule": "",
            },
        )
        self.assertTrue(form.is_valid(), form.errors)
        item = form.save()
        self.assertEqual(item.parent_id, self.reference.pk)


class ItemDetailViewCompletedParentTests(TestCase):
    """End-to-end regression for the reported bug: an item whose parent
    project was completed could not be saved from the detail modal at all —
    the browser re-posted the pre-filled parent id and the form 400'd with
    'Select a valid choice' / 'Parent must be of type: project, reference'."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="u", password="x")
        self.client.force_login(self.user)
        self.project = Item.objects.create(
            title="Old project", status=GTDStatus.PROJECT, user=self.user
        )
        self.child = Item.objects.create(
            title="Child task",
            status=GTDStatus.NEXT_ACTION,
            user=self.user,
            parent=self.project,
        )
        self.project.flow.complete()

    def _post(self, **overrides):
        # What the modal form posts when the user edits without touching the
        # parent field: the autocomplete's hidden input re-submits the
        # stored parent id.
        data = {
            "title": "Child task (edited)",
            "priority": self.child.priority,
            "parent": str(self.project.pk),
            "rrule": "",
        }
        data.update(overrides)
        return self.client.post(
            reverse("item_detail", kwargs={"item_id": self.child.pk}),
            data,
            HTTP_HX_REQUEST="true",
        )

    def test_saving_item_with_completed_parent_succeeds(self):
        response = self._post()
        self.assertEqual(response.status_code, 200)  # 400 before the fix
        self.child.refresh_from_db()
        self.assertEqual(self.child.title, "Child task (edited)")
        self.assertEqual(self.child.parent_id, self.project.pk)

    def test_clearing_completed_parent_succeeds(self):
        response = self._post(parent="")
        self.assertEqual(response.status_code, 200)
        self.child.refresh_from_db()
        self.assertIsNone(self.child.parent_id)

    def test_switching_to_a_completed_parent_still_rejected(self):
        other_done = Item.objects.create(
            title="Other project", status=GTDStatus.PROJECT, user=self.user
        )
        other_done.flow.complete()

        response = self._post(parent=str(other_done.pk))
        self.assertEqual(response.status_code, 400)
        self.child.refresh_from_db()
        self.assertEqual(self.child.parent_id, self.project.pk)
