from django.contrib.auth.models import User
from django.test import TestCase

from nirvana.importer import (
    PHASE_CREATING,
    PHASE_PARENTS,
    PHASE_TAGS,
    NirvanaImporter,
)
from task_processor.constants import GTDEnergy, GTDStatus, Priority
from task_processor.models import Area, Context, Item
from task_processor.models.base_models import Tag


def nirvana_item(**overrides):
    """A minimal valid Nirvana export entry."""
    base = {
        "id": "n-1",
        "name": "A task",
        "note": "",
        "type": 0,
        "state": 0,
        "created": 1700000000,
        "updated": 1700000000,
        "completed": 0,
        "deleted": 0,
        "parentid": "",
        "tags": "",
        "duedate": "",
        "waitingfor": "",
        "energy": "",
    }
    base.update(overrides)
    return base


class TestStatusMapping(TestCase):
    def setUp(self):
        self.importer = NirvanaImporter()

    def test_reference_types_always_reference(self):
        self.assertEqual(
            self.importer.map_nirvana_state_to_gtd_status(1, 2), GTDStatus.REFERENCE
        )
        self.assertEqual(
            self.importer.map_nirvana_state_to_gtd_status(7, 3), GTDStatus.REFERENCE
        )

    def test_project_type_mapping(self):
        self.assertEqual(
            self.importer.map_nirvana_state_to_gtd_status(1, 1), GTDStatus.PROJECT
        )
        self.assertEqual(
            self.importer.map_nirvana_state_to_gtd_status(7, 1), GTDStatus.COMPLETED
        )
        self.assertEqual(
            self.importer.map_nirvana_state_to_gtd_status(10, 1), GTDStatus.PROJECT
        )

    def test_task_state_mapping(self):
        expected = {
            0: GTDStatus.INBOX,
            1: GTDStatus.NEXT_ACTION,
            2: GTDStatus.REFERENCE,
            4: GTDStatus.NEXT_ACTION,
            7: GTDStatus.COMPLETED,
            10: GTDStatus.WAITING_FOR,
            11: GTDStatus.SOMEDAY_MAYBE,
            99: GTDStatus.INBOX,  # unknown state falls back to inbox
        }
        for state, status in expected.items():
            self.assertEqual(
                self.importer.map_nirvana_state_to_gtd_status(state, 0), status
            )

    def test_energy_mapping(self):
        self.assertEqual(NirvanaImporter._map_nirvana_energy(1), GTDEnergy.LOW)
        self.assertEqual(NirvanaImporter._map_nirvana_energy(2), GTDEnergy.MEDIUM)
        self.assertEqual(NirvanaImporter._map_nirvana_energy(3), GTDEnergy.HIGH)
        self.assertIsNone(NirvanaImporter._map_nirvana_energy(""))


class TestImportItems(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="importer", password="x")
        self.importer = NirvanaImporter()

    def test_three_pass_import(self):
        items = [
            nirvana_item(id="p-1", name="Project", type=1, state=1),
            nirvana_item(id="t-1", name="Child", parentid="p-1", tags="home,phone"),
        ]
        result = self.importer.import_items(items, self.user)

        self.assertEqual(result.created, 2)
        self.assertEqual(result.updated, 0)
        self.assertEqual(result.total, 2)

        child = Item.objects.get(nirvana_id="t-1")
        parent = Item.objects.get(nirvana_id="p-1")
        self.assertEqual(child.parent, parent)
        self.assertEqual(parent.status, GTDStatus.PROJECT)
        self.assertSetEqual(
            set(child.tags.values_list("name", flat=True)), {"home", "phone"}
        )

    def test_parent_lookup_is_scoped_to_the_user(self):
        # A crafted export must not attach items under another user's item.
        victim = User.objects.create_user(username="victim", password="x")
        self.importer.import_items([nirvana_item(id="v-1")], victim)

        self.importer.import_items([nirvana_item(id="t-1", parentid="v-1")], self.user)

        attacked = Item.objects.get(nirvana_id="t-1", user=self.user)
        self.assertIsNone(attacked.parent)

    def test_parent_from_a_previous_import_is_linked(self):
        self.importer.import_items([nirvana_item(id="p-1", type=1, state=1)], self.user)
        self.importer.import_items([nirvana_item(id="t-1", parentid="p-1")], self.user)

        child = Item.objects.get(nirvana_id="t-1", user=self.user)
        self.assertEqual(child.parent, Item.objects.get(nirvana_id="p-1"))

    def test_same_nirvana_id_for_two_users(self):
        other = User.objects.create_user(username="twin", password="x")
        self.importer.import_items([nirvana_item(id="t-1")], self.user)
        result = self.importer.import_items([nirvana_item(id="t-1")], other)

        self.assertEqual(result.created, 1)
        self.assertEqual(Item.objects.filter(nirvana_id="t-1").count(), 2)

    def test_reimport_is_idempotent(self):
        items = [nirvana_item(id="t-1", name="Once")]
        self.importer.import_items(items, self.user)
        result = self.importer.import_items(items, self.user)

        self.assertEqual(result.created, 0)
        self.assertEqual(result.updated, 1)
        self.assertEqual(Item.objects.filter(nirvana_id="t-1").count(), 1)

    def test_deleted_items_are_skipped(self):
        items = [nirvana_item(id="t-1", deleted=1)]
        result = self.importer.import_items(items, self.user)

        self.assertEqual(result.total, 0)
        self.assertFalse(Item.objects.exists())

    def test_long_title_is_truncated(self):
        items = [nirvana_item(id="t-1", name="x" * 2000)]
        self.importer.import_items(items, self.user)

        item = Item.objects.get(nirvana_id="t-1")
        self.assertEqual(len(item.title), 1024)
        self.assertTrue(item.title.endswith("..."))

    def test_completed_item(self):
        items = [nirvana_item(id="t-1", state=7, completed=1700000500)]
        self.importer.import_items(items, self.user)

        item = Item.objects.get(nirvana_id="t-1")
        self.assertTrue(item.is_completed)
        self.assertEqual(item.status, GTDStatus.COMPLETED)
        self.assertIsNotNone(item.completed_at)

    def test_progress_callback_receives_all_phases(self):
        calls = []
        importer = NirvanaImporter(progress=lambda *args: calls.append(args))
        items = [nirvana_item(id="t-1"), nirvana_item(id="t-2")]
        importer.import_items(items, self.user)

        self.assertEqual(
            calls,
            [
                (PHASE_CREATING, 1, 2),
                (PHASE_CREATING, 2, 2),
                (PHASE_PARENTS, 1, 2),
                (PHASE_PARENTS, 2, 2),
                (PHASE_TAGS, 1, 2),
                (PHASE_TAGS, 2, 2),
            ],
        )


class TestDeleteExistingData(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="wiped", password="x")
        self.other = User.objects.create_user(username="kept", password="x")
        self.importer = NirvanaImporter()
        for owner in (self.user, self.other):
            area = Area.objects.create(name="Area", user=owner)
            Context.objects.create(name="Ctx", user=owner)
            Tag.objects.create(name="tag", user=owner)
            Item.objects.create(
                title="Item",
                status=GTDStatus.INBOX,
                priority=Priority.NORMAL,
                user=owner,
                area=area,
            )

    def test_wipes_only_the_given_user(self):
        self.importer.delete_existing_data(self.user)

        for model in (Item, Area, Context, Tag):
            self.assertFalse(model.objects.filter(user=self.user).exists())
            self.assertTrue(model.objects.filter(user=self.other).exists())

    def test_dry_run_deletes_nothing(self):
        self.importer.delete_existing_data(self.user, dry_run=True)

        self.assertTrue(Item.objects.filter(user=self.user).exists())
