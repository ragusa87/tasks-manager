import json
import tempfile

from django.contrib.auth.models import User
from django.core.management import CommandError, call_command
from django.test import TestCase

from task_processor.models import Item

from .test_importer import nirvana_item


class TestNirvanaImportCommand(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="cli", password="x")

    def _export_file(self, items):
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        json.dump(items, f)
        f.close()
        return f.name

    def test_imports_items(self):
        path = self._export_file([nirvana_item(id="t-1", name="From CLI")])
        call_command("nirvana_import", path, "cli")

        self.assertTrue(Item.objects.filter(nirvana_id="t-1", user=self.user).exists())

    def test_dry_run_imports_nothing(self):
        path = self._export_file([nirvana_item(id="t-1")])
        call_command("nirvana_import", path, "cli", "--dry-run")

        self.assertFalse(Item.objects.exists())

    def test_delete_flag_wipes_before_import(self):
        old = Item.objects.create(title="Old", user=self.user)
        path = self._export_file([nirvana_item(id="t-1")])
        call_command("nirvana_import", path, "cli", "--delete")

        self.assertFalse(Item.objects.filter(pk=old.pk).exists())
        self.assertTrue(Item.objects.filter(nirvana_id="t-1").exists())

    def test_missing_user_raises(self):
        path = self._export_file([])
        with self.assertRaises(CommandError):
            call_command("nirvana_import", path, "nobody")

    def test_missing_file_raises(self):
        with self.assertRaises(CommandError):
            call_command("nirvana_import", "/does/not/exist.json", "cli")
