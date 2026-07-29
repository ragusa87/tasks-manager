from io import StringIO

from django.core import management
from django.test import TestCase

from task_processor.management.commands.fixturize import DOCUMENTS_ITEM_TITLE
from task_processor.models import Document, Item


class FixturizeDocumentsTests(TestCase):
    def run_command(self):
        out = StringIO()
        management.call_command(
            "fixturize", "--users=2", "--items-per-user=4", stdout=out
        )
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
