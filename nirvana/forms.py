import json

from django import forms
from django.conf import settings


class NirvanaImportForm(forms.Form):
    """Upload a Nirvana JSON export and optionally wipe existing data first."""

    file = forms.FileField(
        label="Nirvana JSON export",
        widget=forms.ClearableFileInput(
            attrs={"class": "input", "accept": ".json,application/json"}
        ),
    )
    wipe_existing = forms.BooleanField(
        required=False,
        label="Wipe existing data before importing",
        help_text=(
            "Permanently deletes ALL your items, areas, contexts and tags "
            "before the import starts."
        ),
    )

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        # The import ingests an uploaded file, so it is gated by the same master
        # switch as document uploads: reject the file, keep the page usable.
        if not settings.ALLOW_FILES_UPLOAD:
            raise forms.ValidationError("File uploads are disabled on this instance.")
        if uploaded.size > settings.MAX_FILE_SIZE:
            max_mb = settings.MAX_FILE_SIZE // (1024 * 1024)
            raise forms.ValidationError(f"File exceeds the {max_mb} MB limit.")
        try:
            data = json.load(uploaded)
        except (json.JSONDecodeError, UnicodeDecodeError, RecursionError):
            raise forms.ValidationError("This is not a valid JSON file.")
        if not isinstance(data, list) or not all(
            isinstance(entry, dict) for entry in data
        ):
            raise forms.ValidationError(
                "Expected a Nirvana export: a JSON list of items."
            )
        uploaded.seek(0)
        return uploaded
