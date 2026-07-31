from django.contrib.auth.models import User
from django.db.models import Q
from django.http import QueryDict
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from task_processor.batch import (
    BATCH_REGISTRY,
    AreaBatchActions,
    ContextBatchActions,
    ItemBatchActions,
    TagBatchActions,
    formless_transition_groups,
)
from task_processor.constants import GTDStatus
from task_processor.forms import BatchTransitionForm
from task_processor.models import Area, Context, Item, Tag
from task_processor.models.item import ItemFlow, batchable


def group_key(label):
    """The formless_transition_groups key of the group with this label."""
    return next(
        key
        for key, group in formless_transition_groups().items()
        if group["label"] == label
    )


def create_item_in_status(user, status, **kwargs):
    """Create an item and force its status/completion flags past save()."""
    item = Item.objects.create(title=f"item-{status}", user=user, **kwargs)
    Item.objects.filter(pk=item.pk).update(
        status=status, is_completed=(status == GTDStatus.COMPLETED)
    )
    item.refresh_from_db()
    return item


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
        self.assertEqual(BATCH_REGISTRY["context"], ContextBatchActions)

    def test_actions_discovered_and_sorted(self):
        actions = ItemBatchActions(self.user).get_available_actions()
        names = [action.name for action in actions]
        # positions: add_tag=20, remove_tag=10, replace_area=5, add_area=4,
        # move=2, convert_to_reference=1, remove_area=-10
        self.assertEqual(
            names,
            [
                "add_tag",
                "remove_tag",
                "replace_area",
                "add_area",
                "move",
                "convert_to_reference",
                "remove_area",
            ],
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


class ContextConversionTests(BatchTestBase):
    def setUp(self):
        super().setUp()
        self.context = Context.objects.create(name="@office", user=self.user)
        self.item = Item.objects.create(title="task", user=self.user)
        self.item.contexts.add(self.context)

    def run_action(self, actions, slug, ids, **form_data):
        action = actions.get_action(slug)
        selection = actions.resolve_selection(selection_data(ids=ids))
        return actions.run(action, selection, **form_data)

    def test_context_to_tag_moves_items(self):
        self.run_action(
            ContextBatchActions(self.user), "convert_to_tag", [self.context.pk]
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.tags.get().name, "@office")
        self.assertEqual(self.item.contexts.count(), 0)
        # delete_source not requested: the emptied context survives
        self.assertTrue(Context.objects.filter(pk=self.context.pk).exists())

    def test_context_to_tag_with_delete_source_and_destination(self):
        destination = Tag.objects.create(name="office-work", user=self.user)
        self.run_action(
            ContextBatchActions(self.user),
            "convert_to_tag",
            [self.context.pk],
            tag=destination,
            delete_source=True,
        )
        self.item.refresh_from_db()
        self.assertEqual(list(self.item.tags.all()), [destination])
        self.assertFalse(Context.objects.filter(pk=self.context.pk).exists())

    def test_context_to_area_skips_items_in_another_area(self):
        other_area = Area.objects.create(name="Personal", user=self.user)
        busy = Item.objects.create(title="busy", user=self.user, area=other_area)
        busy.contexts.add(self.context)

        _, extra = self.run_action(
            ContextBatchActions(self.user),
            "convert_to_area",
            [self.context.pk],
            delete_source=True,
        )

        self.item.refresh_from_db()
        busy.refresh_from_db()
        self.assertEqual(self.item.area.name, "@office")
        self.assertEqual(self.item.contexts.count(), 0)
        self.assertEqual(busy.area, other_area)  # untouched
        self.assertEqual(list(busy.contexts.all()), [self.context])  # kept
        # Context still has an item -> survives despite delete_source
        self.assertTrue(Context.objects.filter(pk=self.context.pk).exists())
        self.assertIn("skipped", extra)

    def test_tag_to_context_moves_items(self):
        tag = Tag.objects.create(name="deep-work", user=self.user)
        self.item.tags.add(tag)
        self.run_action(
            TagBatchActions(self.user),
            "convert_to_context",
            [tag.pk],
            delete_source=True,
        )
        self.item.refresh_from_db()
        self.assertIn("deep-work", self.item.contexts.values_list("name", flat=True))
        self.assertEqual(self.item.tags.count(), 0)
        self.assertFalse(Tag.objects.filter(pk=tag.pk).exists())


class BatchableDecoratorTests(BatchTestBase):
    def test_decorator_sets_metadata(self):
        def condition():
            return Q(pk=1)

        @batchable(filter_q=condition, enabled=False)
        def dummy():
            pass

        self.assertEqual(dummy._batchable, {"filter_q": condition, "enabled": False})

    def test_metadata_readable_through_annotated_property(self):
        # Same read path as _form_class: survives stacking over the
        # viewflow transition decorator.
        flow = ItemFlow(Item())
        for name in ("cancel", "reopen"):
            meta = flow._get_annotated_property(name, "_batchable")
            self.assertIsNotNone(meta, name)
            self.assertTrue(callable(meta["filter_q"]), name)
        self.assertIsNone(flow._get_annotated_property("complete", "_batchable"))


class TransitionGroupTests(BatchTestBase):
    def label_map(self):
        return {
            group["label"]: group for group in formless_transition_groups().values()
        }

    def test_excludes_form_based_transitions(self):
        methods = {
            name
            for group in formless_transition_groups().values()
            for name in group["methods"]
        }
        self.assertNotIn("delegate", methods)
        self.assertNotIn("process_as_reference", methods)
        self.assertNotIn("convert_as_reference", methods)

    def test_expected_group_map(self):
        expected = {
            "Next Action": {"process_as_action", "activate_from_someday_maybe"},
            "Someday/Maybe": {"process_as_someday_maybe", "defer_to_someday_maybe"},
            "Convert to Project": {"process_as_project", "activate_as_project"},
            "Complete": {"complete"},
            "Cancel": {"cancel"},
            "Received Response": {"receive_response"},
            "Reopen": {"reopen"},
            "Restore to Inbox": {"uncancel"},
        }
        actual = {
            label: set(group["methods"]) for label, group in self.label_map().items()
        }
        self.assertEqual(actual, expected)

    def test_group_key_is_first_method_name(self):
        for key, group in formless_transition_groups().items():
            self.assertEqual(key, group["methods"][0])

    def test_enabled_false_excludes_group(self):
        descriptor = ItemFlow.uncancel._descriptor
        descriptor._batchable = {"filter_q": None, "enabled": False}
        try:
            self.assertNotIn("Restore to Inbox", self.label_map())
        finally:
            del descriptor._batchable

    def test_group_q_matches_can_proceed_for_every_status(self):
        """Core property: the SQL filters agree with the FSM's can_proceed
        (incl. cancel's and reopen's python conditions via @batchable)."""
        for status in GTDStatus.values:
            item = create_item_in_status(self.user, status)
            for key, group in formless_transition_groups().items():
                can_proceed = any(
                    getattr(item.flow, name).can_proceed() for name in group["methods"]
                )
                matches_q = Item.objects.filter(group["q"], pk=item.pk).exists()
                self.assertEqual(
                    matches_q, can_proceed, f"group {key} vs status {status}"
                )

    def test_reopen_q_requires_is_completed(self):
        item = create_item_in_status(self.user, GTDStatus.COMPLETED)
        Item.objects.filter(pk=item.pk).update(is_completed=False)
        item.refresh_from_db()
        group = self.label_map()["Reopen"]
        self.assertFalse(item.flow.reopen.can_proceed())
        self.assertFalse(Item.objects.filter(group["q"], pk=item.pk).exists())


class BatchTransitionFormTests(BatchTestBase):
    def setUp(self):
        super().setUp()
        for status in (
            GTDStatus.INBOX,
            GTDStatus.INBOX,
            GTDStatus.SOMEDAY_MAYBE,
            GTDStatus.WAITING_FOR,
            GTDStatus.COMPLETED,
        ):
            create_item_in_status(self.user, status)
        self.selection = Item.objects.filter(user=self.user)

    def counts_by_label(self):
        form = BatchTransitionForm(user=self.user, selection=self.selection)
        counts = {}
        for _key, text in form.fields["transition"].choices:
            label, _sep, count = text.rpartition(" (")
            counts[label] = int(count.rstrip(")"))
        return counts

    def test_choice_counts_for_mixed_selection(self):
        counts = self.counts_by_label()
        self.assertEqual(
            counts,
            {
                "Next Action": 3,  # 2 inbox + 1 someday
                "Someday/Maybe": 3,  # 2 inbox + 1 waiting
                "Convert to Project": 3,  # 2 inbox + 1 someday
                "Complete": 4,  # 2 inbox + someday + waiting
                "Cancel": 5,  # everything (nothing cancelled)
                "Received Response": 1,  # waiting
                "Reopen": 1,  # completed
                # "Restore to Inbox" hidden: no cancelled item selected
                "Delete": 5,  # pseudo-transition: every item is deletable
            },
        )

    def test_delete_choice_is_last(self):
        form = BatchTransitionForm(user=self.user, selection=self.selection)
        self.assertEqual(form.fields["transition"].choices[-1][0], "delete")

    def test_zero_count_groups_hidden(self):
        self.assertNotIn("Restore to Inbox", self.counts_by_label())

    def test_counts_use_a_single_query(self):
        with self.assertNumQueries(1):
            BatchTransitionForm(user=self.user, selection=self.selection)

    def test_invalid_transition_rejected(self):
        form = BatchTransitionForm(
            {"transition": "not_a_transition"},
            user=self.user,
            selection=self.selection,
        )
        self.assertFalse(form.is_valid())


class MoveActionTests(BatchTestBase):
    def move(self, items, label):
        actions = ItemBatchActions(self.user)
        action = actions.get_action("move")
        selection = actions.resolve_selection(
            selection_data(ids=[item.pk for item in items])
        )
        return actions.run(action, selection, transition=group_key(label))

    def test_grouped_dispatch_to_next_action(self):
        inbox = create_item_in_status(self.user, GTDStatus.INBOX)
        someday = create_item_in_status(self.user, GTDStatus.SOMEDAY_MAYBE)

        applied, extra = self.move([inbox, someday], "Next Action")

        inbox.refresh_from_db()
        someday.refresh_from_db()
        self.assertEqual(inbox.status, GTDStatus.NEXT_ACTION)
        self.assertEqual(someday.status, GTDStatus.NEXT_ACTION)
        self.assertEqual(applied, 2)
        self.assertIn("moved to Next Action", extra)

    def test_inapplicable_items_skipped_and_reported(self):
        inbox = create_item_in_status(self.user, GTDStatus.INBOX)
        completed = create_item_in_status(self.user, GTDStatus.COMPLETED)

        applied, extra = self.move([inbox, completed], "Next Action")

        completed.refresh_from_db()
        self.assertEqual(completed.status, GTDStatus.COMPLETED)
        # run() reports what actually transitioned, not the selection size
        self.assertEqual(applied, 1)
        self.assertIn("moved to Next Action", extra)
        self.assertIn("1 skipped", extra)

    def test_complete_sets_flags_and_stops_recurrence(self):
        item = create_item_in_status(self.user, GTDStatus.NEXT_ACTION)
        Item.objects.filter(pk=item.pk).update(
            rrule="FREQ=DAILY", remind_at=timezone.now()
        )

        self.move([item], "Complete")

        item.refresh_from_db()
        self.assertEqual(item.status, GTDStatus.COMPLETED)
        self.assertTrue(item.is_completed)
        self.assertIsNotNone(item.completed_at)
        # post_save signal clears reminder + recurrence, same as a single
        # transition (it only fires when remind_at is set — app behavior)
        self.assertIsNone(item.remind_at)
        self.assertIsNone(item.rrule)

    def test_complete_from_inbox(self):
        inbox = create_item_in_status(self.user, GTDStatus.INBOX)

        applied, _extra = self.move([inbox], "Complete")

        inbox.refresh_from_db()
        self.assertEqual(applied, 1)
        self.assertEqual(inbox.status, GTDStatus.COMPLETED)
        self.assertTrue(inbox.is_completed)
        self.assertIsNotNone(inbox.completed_at)

    def test_cancel_skips_already_cancelled(self):
        inbox = create_item_in_status(self.user, GTDStatus.INBOX)
        cancelled = create_item_in_status(self.user, GTDStatus.CANCELLED)

        _, extra = self.move([inbox, cancelled], "Cancel")

        inbox.refresh_from_db()
        self.assertEqual(inbox.status, GTDStatus.CANCELLED)
        self.assertIn("1 skipped", extra)

    def test_delete_pseudo_transition_deletes_any_status(self):
        inbox = create_item_in_status(self.user, GTDStatus.INBOX)
        completed = create_item_in_status(self.user, GTDStatus.COMPLETED)
        kept = create_item_in_status(self.user, GTDStatus.NEXT_ACTION)

        actions = ItemBatchActions(self.user)
        action = actions.get_action("move")
        selection = actions.resolve_selection(
            selection_data(ids=[inbox.pk, completed.pk])
        )
        applied, extra = actions.run(action, selection, transition="delete")

        self.assertEqual(applied, 2)
        self.assertIn("deleted", extra)
        self.assertFalse(Item.objects.filter(pk__in=[inbox.pk, completed.pk]).exists())
        self.assertTrue(Item.objects.filter(pk=kept.pk).exists())

    def test_delete_pseudo_transition_ignores_other_users_items(self):
        foreign = create_item_in_status(self.other, GTDStatus.INBOX)

        actions = ItemBatchActions(self.user)
        action = actions.get_action("move")
        selection = actions.resolve_selection(selection_data(ids=[foreign.pk]))
        applied, _extra = actions.run(action, selection, transition="delete")

        self.assertEqual(applied, 0)
        self.assertTrue(Item.objects.filter(pk=foreign.pk).exists())

    def test_reopen_only_affects_completed(self):
        completed = create_item_in_status(self.user, GTDStatus.COMPLETED)
        inbox = create_item_in_status(self.user, GTDStatus.INBOX)

        self.move([completed, inbox], "Reopen")

        completed.refresh_from_db()
        inbox.refresh_from_db()
        # Reopen re-clarifies: back to inbox (GTD), not to an actionable state
        self.assertEqual(completed.status, GTDStatus.INBOX)
        self.assertFalse(completed.is_completed)
        self.assertEqual(inbox.status, GTDStatus.INBOX)


class ConvertToReferenceActionTests(BatchTestBase):
    def convert(self, items, parent=None):
        actions = ItemBatchActions(self.user)
        action = actions.get_action("convert_to_reference")
        selection = actions.resolve_selection(
            selection_data(ids=[item.pk for item in items])
        )
        applicable = actions.filter_applicable(action, selection)
        return actions.run(action, applicable, parent=parent)

    def test_converts_inbox_and_next_action_items(self):
        inbox = create_item_in_status(self.user, GTDStatus.INBOX)
        next_action = create_item_in_status(self.user, GTDStatus.NEXT_ACTION)

        applied, _extra = self.convert([inbox, next_action])

        inbox.refresh_from_db()
        next_action.refresh_from_db()
        self.assertEqual(applied, 2)
        self.assertEqual(inbox.status, GTDStatus.REFERENCE)
        self.assertEqual(next_action.status, GTDStatus.REFERENCE)

    def test_other_states_are_not_applicable(self):
        completed = create_item_in_status(self.user, GTDStatus.COMPLETED)
        actions = ItemBatchActions(self.user)
        action = actions.get_action("convert_to_reference")
        selection = actions.resolve_selection(selection_data(ids=[completed.pk]))
        self.assertEqual(actions.filter_applicable(action, selection).count(), 0)

    def test_parent_is_applied(self):
        project = create_item_in_status(self.user, GTDStatus.PROJECT)
        inbox = create_item_in_status(self.user, GTDStatus.INBOX)

        self.convert([inbox], parent=project)

        inbox.refresh_from_db()
        self.assertEqual(inbox.status, GTDStatus.REFERENCE)
        self.assertEqual(inbox.parent_id, project.pk)

    def test_form_parent_choices_scoped_to_user_and_parentable_statuses(self):
        from task_processor.forms import BatchReferenceForm

        project = create_item_in_status(self.user, GTDStatus.PROJECT)
        create_item_in_status(self.user, GTDStatus.INBOX)  # not a valid parent
        create_item_in_status(self.other, GTDStatus.PROJECT)  # foreign

        form = BatchReferenceForm(user=self.user, selection=None)
        queryset = form.fields["parent"].queryset
        self.assertEqual(list(queryset), [project])


class ImpactPreviewTests(BatchTestBase):
    def setUp(self):
        super().setUp()
        self.tag = Tag.objects.create(name="deep-work", user=self.user)
        self.area = Area.objects.create(name="Work", user=self.user)

    def _impact(self, actions, slug, ids):
        action = actions.get_action(slug)
        selection = actions.resolve_selection(selection_data(ids=ids))
        applicable = actions.filter_applicable(action, selection)
        return actions.describe_impact(action, applicable)

    def test_convert_to_area_counts_movable_and_blocked_items(self):
        free = Item.objects.create(title="free", user=self.user)
        busy = Item.objects.create(title="busy", user=self.user, area=self.area)
        free.tags.add(self.tag)
        busy.tags.add(self.tag)

        impact = self._impact(
            TagBatchActions(self.user), "convert_to_area", [self.tag.pk]
        )

        self.assertIn("2 item(s) carry the selected tag(s)", str(impact))
        self.assertIn("1 will be moved", str(impact))
        self.assertIn("1 already have an area", str(impact))

    def test_convert_to_area_without_items(self):
        impact = self._impact(
            TagBatchActions(self.user), "convert_to_area", [self.tag.pk]
        )
        self.assertIn("No items carry", str(impact))

    def test_convert_to_tag_counts_items(self):
        Item.objects.create(title="a", user=self.user, area=self.area)
        Item.objects.create(title="b", user=self.user, area=self.area)

        impact = self._impact(
            AreaBatchActions(self.user), "convert_to_tag", [self.area.pk]
        )

        self.assertIn("2 item(s) will be tagged", str(impact))

    def test_action_without_impact_returns_none(self):
        actions = ItemBatchActions(self.user)
        item = Item.objects.create(title="a", user=self.user)
        self.assertIsNone(self._impact(actions, "add_tag", [item.pk]))


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

    def test_preview_shows_conversion_item_impact(self):
        tag = Tag.objects.create(name="deep-work", user=self.user)
        self.item_a.tags.add(tag)
        self.item_b.tags.add(tag)  # item_b has an area -> blocked
        response = self.client.post(
            self._url(model="tag", slug="convert_to_area"),
            {"ids": [tag.pk]},
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(response, "2 item(s) carry the selected tag(s)")
        self.assertContains(response, "1 will be moved")

    def test_preview_without_impact_has_no_impact_line(self):
        response = self.client.post(
            self._url(),
            {"ids": [self.item_a.pk]},
            HTTP_HX_REQUEST="true",
        )
        self.assertNotContains(response, "will be moved")

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

    def test_move_preview_lists_transitions_with_counts(self):
        response = self.client.post(
            self._url(slug="move"),
            {"ids": [self.item_a.pk, self.item_b.pk]},  # both inbox
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Next Action (2)")
        self.assertContains(response, "Complete (2)")
        self.assertContains(response, "Cancel (2)")
        # Zero-count and form-based transitions are absent
        self.assertNotContains(response, "Received Response")
        self.assertNotContains(response, "Waiting For")
        self.assertNotContains(response, "Convert as Reference")

    def test_move_confirm_executes_transition(self):
        response = self.client.post(
            self._url(slug="move"),
            {
                "ids": [self.item_a.pk, self.item_b.pk],
                "confirm": "1",
                "transition": group_key("Next Action"),
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "refreshItems")
        self.item_a.refresh_from_db()
        self.item_b.refresh_from_db()
        self.assertEqual(self.item_a.status, GTDStatus.NEXT_ACTION)
        self.assertEqual(self.item_b.status, GTDStatus.NEXT_ACTION)

    def test_move_confirm_invalid_transition_returns_400(self):
        response = self.client.post(
            self._url(slug="move"),
            {"ids": [self.item_a.pk], "confirm": "1", "transition": "bogus"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 400)
        self.item_a.refresh_from_db()
        self.assertEqual(self.item_a.status, GTDStatus.INBOX)

    def test_move_select_all_with_query_and_exclusion(self):
        response = self.client.post(
            self._url(slug="move"),
            {
                "select_all": "1",
                "q": "in:inbox",
                "excluded_ids": str(self.item_b.pk),
                "confirm": "1",
                "transition": group_key("Next Action"),
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.item_a.refresh_from_db()
        self.item_b.refresh_from_db()
        self.assertEqual(self.item_a.status, GTDStatus.NEXT_ACTION)
        self.assertEqual(self.item_b.status, GTDStatus.INBOX)

    def test_move_ignores_other_users_items(self):
        foreign = Item.objects.create(title="foreign", user=self.other)
        self.client.post(
            self._url(slug="move"),
            {
                "ids": [foreign.pk],
                "confirm": "1",
                "transition": group_key("Next Action"),
            },
            HTTP_HX_REQUEST="true",
        )
        foreign.refresh_from_db()
        self.assertEqual(foreign.status, GTDStatus.INBOX)

    def test_plain_confirm_redirects_to_return_url(self):
        response = self.client.post(
            self._url(slug="remove_area") + "?returnUrl=/tags/",
            {"ids": [self.item_b.pk], "confirm": "1"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/tags/")

    def test_plain_confirm_rejects_unsafe_return_url(self):
        # returnUrl is caller-controlled: foreign hosts (open redirect) fall
        # back to the dashboard, the action itself still runs.
        response = self.client.post(
            self._url(slug="remove_area") + "?returnUrl=https://evil.example/",
            {"ids": [self.item_b.pk], "confirm": "1"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard"))
        self.item_b.refresh_from_db()
        self.assertIsNone(self.item_b.area)
