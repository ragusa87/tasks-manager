from django.contrib.auth.models import User
from django.http import QueryDict
from django.test import Client, TestCase
from django.urls import reverse

from task_processor.batch import (
    BATCH_REGISTRY,
    AreaBatchActions,
    ItemBatchActions,
    TagBatchActions,
)
from task_processor.constants import GTDStatus
from task_processor.models import Area, Item, Tag


def selection_data(**kwargs):
    """Build a QueryDict payload like a batch POST would carry."""
    data = QueryDict(mutable=True)
    for key, value in kwargs.items():
        if isinstance(value, (list, tuple)):
            data.setlist(key, [str(v) for v in value])
        else:
            data[key] = str(value)
    return data


class BatchTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="user", password="x")
        self.other = User.objects.create_user(username="other", password="x")


class BatchRegistryTests(BatchTestBase):
    def test_registry_contains_all_models(self):
        self.assertEqual(BATCH_REGISTRY["item"], ItemBatchActions)
        self.assertEqual(BATCH_REGISTRY["tag"], TagBatchActions)
        self.assertEqual(BATCH_REGISTRY["area"], AreaBatchActions)

    def test_actions_discovered_and_sorted(self):
        actions = ItemBatchActions(self.user).get_available_actions()
        names = [action.name for action in actions]
        # positions: add_tag=20, remove_tag=10, replace_area=5, add_area=4,
        # remove_area=-10
        self.assertEqual(
            names, ["add_tag", "remove_tag", "replace_area", "add_area", "remove_area"]
        )

    def test_get_action_unknown_returns_none(self):
        self.assertIsNone(ItemBatchActions(self.user).get_action("nope"))

    def test_form_class_resolved_from_string(self):
        from task_processor.forms import BatchAddTagForm

        action = ItemBatchActions(self.user).get_action("add_tag")
        self.assertIs(action.form_class, BatchAddTagForm)


class SelectionResolutionTests(BatchTestBase):
    def setUp(self):
        super().setUp()
        self.actions = ItemBatchActions(self.user)
        self.inbox = Item.objects.create(
            title="inbox item", user=self.user, status=GTDStatus.INBOX
        )
        self.next_action = Item.objects.create(
            title="next item", user=self.user, status=GTDStatus.NEXT_ACTION
        )
        self.foreign = Item.objects.create(
            title="foreign", user=self.other, status=GTDStatus.INBOX
        )

    def test_explicit_ids(self):
        data = selection_data(ids=[self.inbox.pk])
        self.assertQuerySetEqual(
            self.actions.resolve_selection(data), [self.inbox], ordered=False
        )

    def test_explicit_ids_exclude_other_users_objects(self):
        data = selection_data(ids=[self.inbox.pk, self.foreign.pk])
        self.assertQuerySetEqual(
            self.actions.resolve_selection(data), [self.inbox], ordered=False
        )

    def test_comma_separated_ids(self):
        data = selection_data(ids=f"{self.inbox.pk},{self.next_action.pk}")
        self.assertEqual(self.actions.resolve_selection(data).count(), 2)

    def test_select_all_applies_search_query(self):
        data = selection_data(select_all="1", q="in:inbox")
        self.assertQuerySetEqual(
            self.actions.resolve_selection(data), [self.inbox], ordered=False
        )

    def test_select_all_without_query_selects_everything_owned(self):
        data = selection_data(select_all="1")
        self.assertQuerySetEqual(
            self.actions.resolve_selection(data),
            [self.inbox, self.next_action],
            ordered=False,
        )

    def test_select_all_minus_excluded_ids(self):
        data = selection_data(select_all="1", excluded_ids=str(self.inbox.pk))
        self.assertQuerySetEqual(
            self.actions.resolve_selection(data), [self.next_action], ordered=False
        )

    def test_empty_selection(self):
        self.assertEqual(self.actions.resolve_selection(selection_data()).count(), 0)


class ItemBatchActionsTests(BatchTestBase):
    def setUp(self):
        super().setUp()
        self.actions = ItemBatchActions(self.user)
        self.tag = Tag.objects.create(name="urgent", user=self.user)
        self.area = Area.objects.create(name="Work", user=self.user)
        self.item_a = Item.objects.create(title="a", user=self.user)
        self.item_b = Item.objects.create(title="b", user=self.user, area=self.area)

    def run_action(self, slug, ids, **form_data):
        actions = self.actions
        action = actions.get_action(slug)
        selection = actions.resolve_selection(selection_data(ids=ids))
        applicable = actions.filter_applicable(action, selection)
        return actions.run(action, applicable, **form_data)

    def test_add_tag(self):
        applied, _ = self.run_action(
            "add_tag", [self.item_a.pk, self.item_b.pk], tag=self.tag
        )
        self.assertEqual(applied, 2)
        self.assertEqual(self.tag.item_set.count(), 2)

    def test_add_tag_is_idempotent(self):
        self.item_a.tags.add(self.tag)
        self.run_action("add_tag", [self.item_a.pk], tag=self.tag)
        self.assertEqual(self.item_a.tags.count(), 1)

    def test_remove_tag(self):
        self.item_a.tags.add(self.tag)
        self.item_b.tags.add(self.tag)
        applied, _ = self.run_action("remove_tag", [self.item_a.pk], tag=self.tag)
        self.assertEqual(applied, 1)
        self.assertEqual(self.item_a.tags.count(), 0)
        self.assertEqual(self.item_b.tags.count(), 1)

    def test_replace_area_overwrites(self):
        new_area = Area.objects.create(name="Home", user=self.user)
        self.run_action("replace_area", [self.item_a.pk, self.item_b.pk], area=new_area)
        self.item_a.refresh_from_db()
        self.item_b.refresh_from_db()
        self.assertEqual(self.item_a.area, new_area)
        self.assertEqual(self.item_b.area, new_area)

    def test_add_area_only_fills_empty(self):
        new_area = Area.objects.create(name="Home", user=self.user)
        applied, _ = self.run_action(
            "add_area", [self.item_a.pk, self.item_b.pk], area=new_area
        )
        self.item_a.refresh_from_db()
        self.item_b.refresh_from_db()
        self.assertEqual(applied, 1)  # item_b already has an area -> skipped
        self.assertEqual(self.item_a.area, new_area)
        self.assertEqual(self.item_b.area, self.area)

    def test_remove_area(self):
        self.run_action("remove_area", [self.item_b.pk])
        self.item_b.refresh_from_db()
        self.assertIsNone(self.item_b.area)


class TagConversionTests(BatchTestBase):
    def setUp(self):
        super().setUp()
        self.actions = TagBatchActions(self.user)
        self.tag = Tag.objects.create(name="deep-work", user=self.user)
        self.free_item = Item.objects.create(title="free", user=self.user)
        self.free_item.tags.add(self.tag)

    def convert(self, tags, **form_data):
        action = self.actions.get_action("convert_to_area")
        selection = self.actions.resolve_selection(
            selection_data(ids=[t.pk for t in tags])
        )
        return self.actions.run(action, selection, **form_data)

    def test_convert_creates_area_moves_item_detaches_tag(self):
        self.convert([self.tag])
        area = Area.objects.get(name="deep-work", user=self.user)
        self.free_item.refresh_from_db()
        self.assertEqual(self.free_item.area, area)
        self.assertEqual(self.free_item.tags.count(), 0)
        # delete_source not requested: the (empty) tag survives
        self.assertTrue(Tag.objects.filter(pk=self.tag.pk).exists())

    def test_convert_reuses_existing_area_with_same_name(self):
        existing = Area.objects.create(name="deep-work", user=self.user)
        self.convert([self.tag])
        self.free_item.refresh_from_db()
        self.assertEqual(self.free_item.area, existing)
        self.assertEqual(Area.objects.filter(user=self.user).count(), 1)

    def test_convert_into_picked_destination(self):
        destination = Area.objects.create(name="Work", user=self.user)
        self.convert([self.tag], area=destination)
        self.free_item.refresh_from_db()
        self.assertEqual(self.free_item.area, destination)
        # No per-tag area created
        self.assertFalse(Area.objects.filter(name="deep-work").exists())

    def test_conflicting_item_is_skipped_and_keeps_tag(self):
        other_area = Area.objects.create(name="Personal", user=self.user)
        busy_item = Item.objects.create(title="busy", user=self.user, area=other_area)
        busy_item.tags.add(self.tag)

        _, extra = self.convert([self.tag], delete_source=True)

        busy_item.refresh_from_db()
        self.assertEqual(busy_item.area, other_area)  # untouched
        self.assertEqual(list(busy_item.tags.all()), [self.tag])  # tag kept
        # Tag still has an item -> survives despite delete_source
        self.assertTrue(Tag.objects.filter(pk=self.tag.pk).exists())
        self.assertIn("skipped", extra)

    def test_item_already_in_destination_area_just_loses_tag(self):
        destination = Area.objects.create(name="Work", user=self.user)
        self.free_item.area = destination
        self.free_item.save()
        self.convert([self.tag], area=destination, delete_source=True)
        self.free_item.refresh_from_db()
        self.assertEqual(self.free_item.area, destination)
        self.assertEqual(self.free_item.tags.count(), 0)
        self.assertFalse(Tag.objects.filter(pk=self.tag.pk).exists())

    def test_delete_source_removes_emptied_tag(self):
        self.convert([self.tag], delete_source=True)
        self.assertFalse(Tag.objects.filter(pk=self.tag.pk).exists())

    def test_overlapping_tags_never_overwrite_each_other(self):
        second = Tag.objects.create(name="admin", user=self.user)
        self.free_item.tags.add(second)

        self.convert([self.tag, second])

        self.free_item.refresh_from_db()
        # Whichever tag converted first claimed the item; the other was
        # skipped, so the item keeps exactly that tag and is never moved twice.
        self.assertIn(self.free_item.area.name, ["deep-work", "admin"])
        remaining_tags = list(self.free_item.tags.values_list("name", flat=True))
        self.assertEqual(len(remaining_tags), 1)
        self.assertNotEqual(remaining_tags[0], self.free_item.area.name)


class AreaConversionTests(BatchTestBase):
    def setUp(self):
        super().setUp()
        self.actions = AreaBatchActions(self.user)
        self.area = Area.objects.create(name="Work", user=self.user)
        self.item = Item.objects.create(title="task", user=self.user, area=self.area)

    def convert(self, areas, **form_data):
        action = self.actions.get_action("convert_to_tag")
        selection = self.actions.resolve_selection(
            selection_data(ids=[a.pk for a in areas])
        )
        return self.actions.run(action, selection, **form_data)

    def test_convert_tags_items_and_clears_area(self):
        self.convert([self.area])
        self.item.refresh_from_db()
        self.assertIsNone(self.item.area)
        self.assertEqual(self.item.tags.get().name, "Work")
        self.assertTrue(Area.objects.filter(pk=self.area.pk).exists())

    def test_convert_with_delete_source(self):
        self.convert([self.area], delete_source=True)
        self.assertFalse(Area.objects.filter(pk=self.area.pk).exists())

    def test_convert_into_picked_destination(self):
        destination = Tag.objects.create(name="work-stuff", user=self.user)
        self.convert([self.area], tag=destination)
        self.item.refresh_from_db()
        self.assertEqual(list(self.item.tags.all()), [destination])
        self.assertFalse(Tag.objects.filter(name="Work").exists())

    def test_long_area_name_truncated_to_tag_length(self):
        long_name = "x" * 60  # Area allows 100 chars, Tag only 50
        area = Area.objects.create(name=long_name, user=self.user)
        item = Item.objects.create(title="t", user=self.user, area=area)
        self.convert([area])
        item.refresh_from_db()
        self.assertEqual(item.tags.get().name, "x" * 50)


class BatchActionViewTests(BatchTestBase):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.force_login(self.user)
        self.tag = Tag.objects.create(name="urgent", user=self.user)
        self.area = Area.objects.create(name="Work", user=self.user)
        self.item_a = Item.objects.create(title="a", user=self.user)
        self.item_b = Item.objects.create(title="b", user=self.user, area=self.area)

    def _url(self, model="item", slug="add_tag"):
        return reverse(
            "batch_action", kwargs={"model_name": model, "action_slug": slug}
        )

    # --- routing / permissions ---------------------------------------------

    def test_login_required(self):
        self.client.logout()
        response = self.client.post(self._url(), {"ids": [self.item_a.pk]})
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_unknown_model_404(self):
        response = self.client.post(self._url(model="context"), {})
        self.assertEqual(response.status_code, 404)

    def test_unknown_action_404(self):
        response = self.client.post(self._url(slug="explode"), {})
        self.assertEqual(response.status_code, 404)

    def test_get_not_allowed(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 405)

    # --- preview -------------------------------------------------------------

    def test_htmx_preview_renders_modal_with_counts_and_echo(self):
        response = self.client.post(
            self._url(slug="add_area"),
            {"ids": [self.item_a.pk, self.item_b.pk]},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "batch/_modal.html")
        # add_area applies only to the item without an area
        self.assertContains(response, "1 of the 2 selected")
        self.assertContains(response, "will be skipped")
        # Selection echoed as hidden fields + confirm flag
        self.assertContains(response, f'name="ids" value="{self.item_a.pk}"')
        self.assertContains(response, 'name="confirm" value="1"')
        # Nothing executed yet
        self.item_a.refresh_from_db()
        self.assertIsNone(self.item_a.area)

    def test_preview_shows_action_description(self):
        response = self.client.post(
            self._url(slug="add_area"),
            {"ids": [self.item_a.pk]},
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(response, "Sets the area on items that have none")

    def test_plain_preview_renders_full_page(self):
        response = self.client.post(self._url(), {"ids": [self.item_a.pk]})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "batch/form.html")

    def test_preview_with_empty_selection_has_no_confirm_button(self):
        response = self.client.post(self._url(), {}, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nothing is selected")
        self.assertNotContains(response, 'name="confirm"')

    # --- confirm -------------------------------------------------------------

    def test_confirm_add_tag_executes_and_refreshes_list(self):
        response = self.client.post(
            self._url(),
            {"ids": [self.item_a.pk], "confirm": "1", "tag": self.tag.pk},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "refreshItems")
        self.assertEqual(list(self.item_a.tags.all()), [self.tag])

    def test_confirm_without_form_action(self):
        response = self.client.post(
            self._url(slug="remove_area"),
            {"ids": [self.item_b.pk], "confirm": "1"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.item_b.refresh_from_db()
        self.assertIsNone(self.item_b.area)

    def test_confirm_invalid_form_returns_400(self):
        response = self.client.post(
            self._url(),
            {"ids": [self.item_a.pk], "confirm": "1"},  # missing tag
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 400)
        self.assertTemplateUsed(response, "batch/_modal.html")
        self.assertEqual(self.item_a.tags.count(), 0)

    def test_confirm_select_all_with_query_and_exclusion(self):
        response = self.client.post(
            self._url(slug="replace_area"),
            {
                "select_all": "1",
                "q": "",
                "excluded_ids": str(self.item_b.pk),
                "confirm": "1",
                "area": self.area.pk,
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.item_a.refresh_from_db()
        self.assertEqual(self.item_a.area, self.area)

    def test_confirm_ignores_other_users_ids(self):
        foreign = Item.objects.create(title="foreign", user=self.other)
        self.client.post(
            self._url(),
            {"ids": [foreign.pk], "confirm": "1", "tag": self.tag.pk},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(foreign.tags.count(), 0)

    def test_form_choices_scoped_to_user(self):
        foreign_tag = Tag.objects.create(name="foreign", user=self.other)
        response = self.client.post(
            self._url(),
            {"ids": [self.item_a.pk], "confirm": "1", "tag": foreign_tag.pk},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.item_a.tags.count(), 0)

    def test_confirm_tag_conversion_answers_with_page_refresh(self):
        item = Item.objects.create(title="tagged", user=self.user)
        tag = Tag.objects.create(name="deep-work", user=self.user)
        item.tags.add(tag)
        response = self.client.post(
            self._url(model="tag", slug="convert_to_area"),
            {"ids": [tag.pk], "confirm": "1"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers.get("HX-Refresh"), "true")
        item.refresh_from_db()
        self.assertEqual(item.area.name, "deep-work")
        self.assertEqual(item.tags.count(), 0)

    def test_plain_confirm_redirects_to_return_url(self):
        response = self.client.post(
            self._url(slug="remove_area") + "?returnUrl=/tags/",
            {"ids": [self.item_b.pk], "confirm": "1"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/tags/")
