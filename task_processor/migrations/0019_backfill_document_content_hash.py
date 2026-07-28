"""Backfill content_hash for documents uploaded before hashing existed.

Streams each stored file through SHA-256; documents whose file is missing
from storage are left with an empty hash (they can never collide, so dedup
simply doesn't apply to them).
"""

import hashlib

from django.db import migrations


def backfill_hashes(apps, schema_editor):
    Document = apps.get_model("task_processor", "Document")
    for document in Document.objects.filter(content_hash="").iterator():
        try:
            with document.file.open("rb") as fh:
                hasher = hashlib.sha256()
                for chunk in fh.chunks():
                    hasher.update(chunk)
        except (FileNotFoundError, ValueError, OSError):
            continue
        document.content_hash = hasher.hexdigest()
        document.save(update_fields=["content_hash"])


class Migration(migrations.Migration):
    dependencies = [
        ("task_processor", "0018_document_content_hash"),
    ]

    operations = [
        migrations.RunPython(backfill_hashes, migrations.RunPython.noop),
    ]
