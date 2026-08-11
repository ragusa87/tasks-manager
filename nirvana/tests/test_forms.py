import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from nirvana.forms import NirvanaImportForm


def upload(content: bytes, name="export.json"):
    return SimpleUploadedFile(name, content, content_type="application/json")


class TestNirvanaImportForm(TestCase):
    def _form(self, file, wipe=False):
        return NirvanaImportForm(data={"wipe_existing": wipe}, files={"file": file})

    def test_valid_json_list_accepted(self):
        form = self._form(upload(json.dumps([{"id": "1"}]).encode()))
        self.assertTrue(form.is_valid())
        # File pointer is reset so the view can save the full content.
        self.assertEqual(form.cleaned_data["file"].read(), b'[{"id": "1"}]')

    def test_non_json_rejected(self):
        form = self._form(upload(b"definitely not json"))
        self.assertFalse(form.is_valid())
        self.assertIn("not a valid JSON file", form.errors["file"][0])

    def test_json_dict_rejected(self):
        form = self._form(upload(b'{"not": "a list"}'))
        self.assertFalse(form.is_valid())
        self.assertIn("JSON list", form.errors["file"][0])

    def test_list_of_non_dicts_rejected(self):
        # Would otherwise crash the worker on item.get(...).
        form = self._form(upload(b"[1, 2, 3]"))
        self.assertFalse(form.is_valid())
        self.assertIn("JSON list", form.errors["file"][0])

    @override_settings(MAX_FILE_SIZE=4)
    def test_oversize_rejected(self):
        form = self._form(upload(b"[1, 2, 3]"))
        self.assertFalse(form.is_valid())
        self.assertIn("exceeds", form.errors["file"][0])

    def test_wipe_defaults_to_false(self):
        form = self._form(upload(b"[]"))
        self.assertTrue(form.is_valid())
        self.assertFalse(form.cleaned_data["wipe_existing"])
