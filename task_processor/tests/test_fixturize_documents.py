from io import StringIO

from django.core import management
from django.test import TestCase, override_settings

from task_processor.management.commands.fixturize import DOCUMENTS_ITEM_TITLE
from task_processor.models import Document, Item

IN_MEMORY_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


class FixturizeDocumentsTests(TestCase):
    def run_command(self):
        out = StringIO()
        management.call_command("fixturize", "--items-per-user=4", stdout=out)
        return out.getvalue()

    def test_every_user_gets_the_documents_item(self):
        self.run_command()

        for username in ("user1", "user2"):
            item = Item.objects.get(title=DOCUMENTS_ITEM_TITLE, user__username=username)
            documents = item.documents.all()
            self.assertEqual(documents.count(), 3)
            # attach_document sniffs the content type from the bytes, so this
            # also proves the generated samples pass the upload validation.
            self.assertCountEqual(
                [d.content_type.split("/")[0] for d in documents],
                ["application", "image", "audio"],
            )

    def test_rerun_is_idempotent(self):
        self.run_command()
        self.run_command()
        self.assertEqual(Item.objects.filter(title=DOCUMENTS_ITEM_TITLE).count(), 2)
        self.assertEqual(Document.objects.count(), 6)

    @override_settings(ALLOW_FILES_UPLOAD=False)
    def test_seeds_documents_even_when_uploads_disabled(self):
        # The upload flag gates user-facing entry points, not internal seeding:
        # the demo still ships sample documents to showcase (read-only).
        self.run_command()
        item = Item.objects.get(title=DOCUMENTS_ITEM_TITLE, user__username="user1")
        self.assertEqual(item.documents.count(), 3)


@override_settings(STORAGES=IN_MEMORY_STORAGES)
class FixturizeDocumentFileCleanupTests(TestCase):
    """The demo self-resets with `fixturize --clear`, which deletes documents
    through the ORM before dropping tables so the stored files are purged (a raw
    DROP TABLE would orphan them and fill the disk). We can't run the full
    --clear here (the test DB has migrations disabled), so we exercise the
    exact ORM delete step and assert the files leave storage."""

    def test_bulk_deleting_documents_removes_their_files(self):
        management.call_command("fixturize", "--items-per-user=1", stdout=StringIO())
        documents = list(Document.objects.all())
        self.assertTrue(documents)
        storage = documents[0].file.storage
        names = [d.file.name for d in documents]
        for name in names:
            self.assertTrue(storage.exists(name))

        Document.objects.all().delete()  # the step clear_data() runs before dropping

        for name in names:
            self.assertFalse(storage.exists(name))
