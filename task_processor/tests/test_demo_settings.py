import importlib
import os
from unittest import mock

from django.test import TestCase


def _load_demo():
    """(Re)import the demo settings module so it re-reads os.environ. It is not
    the active settings module, so importing it doesn't reconfigure Django."""
    import core.settings.demo as demo

    return importlib.reload(demo)


class DemoSettingsTests(TestCase):
    def test_enforces_demo_mode_and_disables_uploads(self):
        demo = _load_demo()
        self.assertIs(demo.IS_DEMO, True)
        self.assertIs(demo.ALLOW_FILES_UPLOAD, False)

    def test_runs_on_sqlite(self):
        demo = _load_demo()
        self.assertTrue(demo.DATABASES["default"]["ENGINE"].endswith("sqlite3"))

    def test_sqlite_path_has_a_default(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("SQLITE_DB_PATH", None)
            demo = _load_demo()
        self.assertTrue(demo.DATABASES["default"]["NAME"].endswith("data/db.sqlite3"))

    def test_sqlite_path_is_env_overridable(self):
        with mock.patch.dict(os.environ, {"SQLITE_DB_PATH": "/custom/demo.sqlite3"}):
            demo = _load_demo()
        self.assertEqual(demo.DATABASES["default"]["NAME"], "/custom/demo.sqlite3")

    def test_banner_has_a_default(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("INSTANCE_BANNER", None)
            demo = _load_demo()
        self.assertIn("demo", demo.INSTANCE_BANNER.lower())

    def test_banner_is_env_overridable(self):
        with mock.patch.dict(os.environ, {"INSTANCE_BANNER": "Custom notice"}):
            demo = _load_demo()
        self.assertEqual(demo.INSTANCE_BANNER, "Custom notice")
