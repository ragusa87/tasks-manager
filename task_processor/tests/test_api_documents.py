import hashlib
import io

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings

from task_processor.constants import GTDStatus, Priority
from task_processor.models import ApiKey, Document, Item
from task_processor.tests.test_documents import make_pdf, make_png
from task_processor.uploads import DocumentValidationError, attach_document

STORAGES_OVERRIDE = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(STORAGES=STORAGES_OVERRIDE)
class TestAttachDocumentUnit(TestCase):
    """Unit tests for the shared attach_document() helper (web view + API)."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        self.item = Item.objects.create(
            title="Test item",
            status=GTDStatus.INBOX,
            priority=Priority.NORMAL,
            user=self.user,
        )

    def test_valid_pdf_creates_document(self):
        content = make_pdf()
        document = attach_document(
            self.item, self.user, SimpleUploadedFile("report.pdf", content)
        )
        self.assertEqual(document.item, self.item)
        self.assertEqual(document.user, self.user)
        self.assertEqual(document.file_name, "report.pdf")
        self.assertEqual(document.file_size, len(content))
        self.assertEqual(document.content_type, "application/pdf")
        self.assertEqual(document.content_hash, hashlib.sha256(content).hexdigest())

    @override_settings(MAX_FILE_SIZE=16)
    def test_oversize_file_raises(self):
        with self.assertRaisesMessage(DocumentValidationError, "exceeds"):
            attach_document(
                self.item, self.user, SimpleUploadedFile("big.pdf", make_pdf())
            )
        self.assertEqual(Document.objects.count(), 0)

    def test_disallowed_type_raises(self):
        # A shell script named .pdf: magic bytes win over the file name.
        with self.assertRaisesMessage(DocumentValidationError, "file type not allowed"):
            attach_document(
                self.item,
                self.user,
                SimpleUploadedFile("script.pdf", b"#!/bin/sh\necho hello\n"),
            )
        self.assertEqual(Document.objects.count(), 0)

    def test_duplicate_content_on_same_item_raises(self):
        content = make_pdf()
        attach_document(self.item, self.user, SimpleUploadedFile("a.pdf", content))
        with self.assertRaisesMessage(
            DocumentValidationError, "identical file already attached"
        ):
            attach_document(
                self.item, self.user, SimpleUploadedFile("renamed.pdf", content)
            )
        self.assertEqual(Document.objects.count(), 1)

    def test_batch_hashes_deduplicates_within_batch(self):
        content = make_pdf()
        batch_hashes = set()
        attach_document(
            self.item,
            self.user,
            SimpleUploadedFile("a.pdf", content),
            batch_hashes=batch_hashes,
        )
        self.assertIn(hashlib.sha256(content).hexdigest(), batch_hashes)

        other_item = Item.objects.create(
            title="Other item", status=GTDStatus.INBOX, user=self.user
        )
        with self.assertRaisesMessage(
            DocumentValidationError, "identical file already attached"
        ):
            attach_document(
                other_item,
                self.user,
                SimpleUploadedFile("b.pdf", content),
                batch_hashes=batch_hashes,
            )

    def test_same_content_on_different_item_succeeds(self):
        content = make_pdf()
        other_item = Item.objects.create(
            title="Other item", status=GTDStatus.INBOX, user=self.user
        )
        attach_document(self.item, self.user, SimpleUploadedFile("a.pdf", content))
        attach_document(other_item, self.user, SimpleUploadedFile("a.pdf", content))
        self.assertEqual(Document.objects.count(), 2)


@override_settings(STORAGES=STORAGES_OVERRIDE)
class TestUploadDocumentEndpoint(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        self.other_user = User.objects.create_user(
            username="otheruser", email="other@example.com", password="testpass"
        )
        self.item = Item.objects.create(
            title="Test item",
            status=GTDStatus.INBOX,
            priority=Priority.NORMAL,
            user=self.user,
        )
        _, self.raw_key = ApiKey.generate(self.user, "test key")
        self.headers = {"Authorization": f"Bearer {self.raw_key}"}

    def post_file(self, item_id, name, content, headers=None):
        file = io.BytesIO(content)
        file.name = name
        return self.client.post(
            f"/api/items/{item_id}/documents",
            {"file": file},
            headers=self.headers if headers is None else headers,
        )

    def test_upload_pdf_returns_201_with_document(self):
        content = make_pdf()
        response = self.post_file(self.item.id, "report.pdf", content)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("id", data)
        self.assertEqual(data["item"], self.item.id)
        self.assertEqual(data["file_name"], "report.pdf")
        self.assertEqual(data["file_size"], len(content))
        self.assertEqual(data["content_type"], "application/pdf")
        self.assertIn("uploaded_at", data)

        document = Document.objects.get(pk=data["id"])
        self.assertEqual(document.user, self.user)
        self.assertEqual(document.item, self.item)

    def test_upload_png_detects_content_type(self):
        response = self.post_file(self.item.id, "pixel.png", make_png())
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["content_type"], "image/png")

    @override_settings(ALLOW_FILES_UPLOAD=False)
    def test_upload_disabled_returns_503(self):
        response = self.post_file(self.item.id, "report.pdf", make_pdf())
        self.assertEqual(response.status_code, 503)
        self.assertEqual(Document.objects.count(), 0)

    def test_missing_auth_returns_401(self):
        response = self.post_file(self.item.id, "report.pdf", make_pdf(), headers={})
        self.assertEqual(response.status_code, 401)

    def test_bogus_token_returns_401(self):
        response = self.post_file(
            self.item.id,
            "report.pdf",
            make_pdf(),
            headers={"Authorization": "Bearer bogus"},
        )
        self.assertEqual(response.status_code, 401)

    def test_unknown_item_returns_404(self):
        response = self.post_file(999999, "report.pdf", make_pdf())
        self.assertEqual(response.status_code, 404)

    def test_foreign_item_returns_404_and_creates_nothing(self):
        other_item = Item.objects.create(
            title="Other item", status=GTDStatus.INBOX, user=self.other_user
        )
        response = self.post_file(other_item.id, "report.pdf", make_pdf())
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Document.objects.count(), 0)

    @override_settings(MAX_FILE_SIZE=16)
    def test_oversize_file_returns_422(self):
        response = self.post_file(self.item.id, "big.pdf", make_pdf())
        self.assertEqual(response.status_code, 422)
        self.assertIn("exceeds", response.json()["detail"])
        self.assertEqual(Document.objects.count(), 0)

    def test_disallowed_type_returns_422(self):
        response = self.post_file(
            self.item.id, "script.pdf", b"#!/bin/sh\necho hello\n"
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("file type not allowed", response.json()["detail"])
        self.assertEqual(Document.objects.count(), 0)

    def test_duplicate_content_returns_422(self):
        content = make_pdf()
        first = self.post_file(self.item.id, "report.pdf", content)
        self.assertEqual(first.status_code, 201)
        second = self.post_file(self.item.id, "renamed.pdf", content)
        self.assertEqual(second.status_code, 422)
        self.assertIn("identical file already attached", second.json()["detail"])
        self.assertEqual(Document.objects.count(), 1)

    def test_missing_file_part_returns_422(self):
        response = self.client.post(
            f"/api/items/{self.item.id}/documents", {}, headers=self.headers
        )
        self.assertEqual(response.status_code, 422)

    def test_session_auth_upload_returns_201(self):
        # The offload page uploads with the session cookie, no bearer key.
        self.client.force_login(self.user)
        file = io.BytesIO(make_png())
        file.name = "pixel.png"
        response = self.client.post(
            f"/api/items/{self.item.id}/documents", {"file": file}
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Document.objects.get().user, self.user)
