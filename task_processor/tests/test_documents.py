import io


def make_pdf(content=b"PDF test content") -> bytes:
    """Return a minimal valid PDF binary that python-magic will recognise as application/pdf."""
    body = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
        b"xref\n0 4\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"trailer\n<< /Size 4 /Root 1 0 R >>\n"
        b"startxref\n190\n%%EOF\n"
    )
    return body


from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from task_processor.constants import GTDStatus, Priority
from task_processor.models import Document, Item


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)
class DocumentUploadViewTests(TestCase):
    """Test the DocumentUploadView"""

    def setUp(self):
        """Set up test data"""
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

    def test_upload_requires_login(self):
        """Test that upload requires login"""
        response = self.client.post(
            reverse("document_upload", args=[self.item.id]),
            {},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_upload_user_isolation(self):
        """Test that users can only upload to their own items"""
        other_item = Item.objects.create(
            title="Other item",
            status=GTDStatus.INBOX,
            priority=Priority.NORMAL,
            user=self.other_user,
        )
        self.client.force_login(self.user)

        pdf_content = b"fake pdf content"
        pdf_file = io.BytesIO(pdf_content)
        pdf_file.name = "test.pdf"

        response = self.client.post(
            reverse("document_upload", args=[other_item.id]),
            {"files": pdf_file},
        )
        self.assertEqual(response.status_code, 404)

    def test_upload_pdf_success(self):
        """Test successful PDF upload"""
        self.client.force_login(self.user)

        pdf_file = io.BytesIO(make_pdf())
        pdf_file.name = "test.pdf"

        response = self.client.post(
            reverse("document_upload", args=[self.item.id]),
            {"files": pdf_file},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Document.objects.count(), 1)
        document = Document.objects.first()
        self.assertEqual(document.file_name, "test.pdf")
        self.assertEqual(document.item, self.item)
        self.assertEqual(document.user, self.user)

    def test_upload_multiple_files(self):
        """Test uploading multiple files"""
        self.client.force_login(self.user)

        pdf1 = io.BytesIO(make_pdf())
        pdf1.name = "test1.pdf"
        pdf2 = io.BytesIO(make_pdf())
        pdf2.name = "test2.pdf"

        response = self.client.post(
            reverse("document_upload", args=[self.item.id]),
            {"files": [pdf1, pdf2]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Document.objects.count(), 2)

    def test_upload_returns_document_list_html(self):
        """Test that upload returns HTML of document list"""
        self.client.force_login(self.user)

        pdf_file = io.BytesIO(make_pdf())
        pdf_file.name = "test.pdf"

        response = self.client.post(
            reverse("document_upload", args=[self.item.id]),
            {"files": pdf_file},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "test.pdf")
        self.assertContains(response, "document-list")


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)
class DocumentDeleteViewTests(TestCase):
    """Test the DocumentDeleteView"""

    def setUp(self):
        """Set up test data"""
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
        pdf_content = b"%PDF-1.4 fake pdf content"
        self.document = Document.objects.create(
            item=self.item,
            file_name="test.pdf",
            file_size=len(pdf_content),
            content_type="application/pdf",
            user=self.user,
        )
        self.document.file.save("test.pdf", io.BytesIO(pdf_content))

    def test_delete_requires_login(self):
        """Test that delete requires login"""
        response = self.client.post(
            reverse("document_delete", args=[self.document.id]),
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_delete_user_isolation(self):
        """Test that users can only delete their own documents"""
        other_item = Item.objects.create(
            title="Other item",
            status=GTDStatus.INBOX,
            priority=Priority.NORMAL,
            user=self.other_user,
        )
        other_pdf = b"%PDF-1.4 other pdf"
        other_document = Document.objects.create(
            item=other_item,
            file_name="other.pdf",
            file_size=len(other_pdf),
            content_type="application/pdf",
            user=self.other_user,
        )
        other_document.file.save("other.pdf", io.BytesIO(other_pdf))
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("document_delete", args=[other_document.id]),
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Document.objects.count(), 2)

    def test_delete_success(self):
        """Test successful document deletion"""
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("document_delete", args=[self.document.id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Document.objects.count(), 0)

    def test_delete_returns_document_list_html(self):
        """Test that delete returns HTML of updated document list"""
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("document_delete", args=[self.document.id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "test.pdf")
        self.assertContains(response, "No documents attached")

    def test_delete_last_document_shows_empty_message(self):
        """Test that deleting last document shows 'No documents attached'"""
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("document_delete", args=[self.document.id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No documents attached")


class ItemDetailViewDocumentTests(TestCase):
    """Test that ItemDetailView includes documents in context"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        self.item = Item.objects.create(
            title="Test item",
            status=GTDStatus.INBOX,
            priority=Priority.NORMAL,
            user=self.user,
        )
        pdf_content = b"fake pdf content"
        self.document = Document.objects.create(
            item=self.item,
            file_name="test.pdf",
            file_size=len(pdf_content),
            user=self.user,
        )
        self.document.file.save("test.pdf", io.BytesIO(pdf_content))

    def test_detail_view_includes_documents(self):
        """Test that ItemDetailView includes documents in context"""
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("item_detail", args=[self.item.id]),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("documents", response.context)
        self.assertEqual(len(response.context["documents"]), 1)
        self.assertEqual(response.context["documents"][0], self.document)

    def test_detail_view_documents_user_isolation(self):
        """Test that documents in detail view are user-isolated"""
        other_user = User.objects.create_user(
            username="other", email="other@example.com", password="testpass"
        )
        other_item = Item.objects.create(
            title="Other item",
            status=GTDStatus.INBOX,
            priority=Priority.NORMAL,
            user=other_user,
        )
        other_doc = Document.objects.create(
            item=other_item,
            file_name="other.pdf",
            file_size=1024,
            user=other_user,
        )
        other_doc.file.save("other.pdf", io.BytesIO(b"content"))
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("item_detail", args=[self.item.id]),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["documents"]), 1)
        self.assertEqual(response.context["documents"][0].file_name, "test.pdf")


@override_settings(
    STORAGE_BACKEND="django.core.files.storage.FileSystemStorage",
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
)
class DocumentDownloadViewTests(TestCase):
    """Test the DocumentDownloadView"""

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
        pdf_content = b"%PDF-1.4 fake pdf content"
        self.document = Document.objects.create(
            item=self.item,
            file_name="test.pdf",
            file_size=len(pdf_content),
            content_type="application/pdf",
            user=self.user,
        )
        self.document.file.save("test.pdf", io.BytesIO(pdf_content))

    def test_download_requires_login(self):
        """Unauthenticated requests are redirected to login"""
        response = self.client.get(
            reverse("document_download", args=[self.document.id]),
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_download_other_user_gets_403(self):
        """A user who does not own the document receives 403"""
        self.client.force_login(self.other_user)
        response = self.client.get(
            reverse("document_download", args=[self.document.id]),
        )
        self.assertEqual(response.status_code, 403)

    def test_download_nonexistent_document_gets_404(self):
        """Requesting a non-existent document ID returns 404"""
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("document_download", args=[99999]),
        )
        self.assertEqual(response.status_code, 404)

    def test_download_local_streams_file(self):
        """Owner receives a streamed FileResponse with correct content type"""
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("document_download", args=[self.document.id]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(
            b"".join(response.streaming_content), b"%PDF-1.4 fake pdf content"
        )

    def test_download_local_no_content_type_falls_back_to_octet_stream(self):
        """When content_type is blank, falls back to application/octet-stream"""
        self.document.content_type = ""
        self.document.save()
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("document_download", args=[self.document.id]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/octet-stream")

    @override_settings(
        STORAGE_BACKEND="storages.backends.s3boto3.S3Boto3Storage",
        AWS_ACCESS_KEY_ID="test-key",
        AWS_SECRET_ACCESS_KEY="test-secret",
        AWS_S3_ENDPOINT_URL="https://s3.example.com",
        AWS_S3_REGION_NAME="eu-west-1",
        AWS_STORAGE_BUCKET_NAME="test-bucket",
        DOCUMENT_PRESIGNED_URL_EXPIRY=300,
    )
    def test_download_s3_redirects_to_presigned_url(self):
        """Owner is redirected to a presigned S3 URL when using S3 storage"""
        presigned_url = (
            "https://s3.example.com/test-bucket/test.pdf?X-Amz-Signature=abc"
        )
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = presigned_url

        with patch("boto3.client", return_value=mock_s3):
            self.client.force_login(self.user)
            response = self.client.get(
                reverse("document_download", args=[self.document.id]),
            )

            self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], presigned_url)
        mock_s3.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={
                "Bucket": "test-bucket",
                "Key": self.document.file.name,
            },
            ExpiresIn=300,
        )


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)
class DocumentCascadeDeleteTests(TestCase):
    """Test that deleting an Item also deletes associated Document files."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser2", email="test2@example.com", password="testpass"
        )
        self.item = Item.objects.create(
            title="Item with docs",
            user=self.user,
            status=GTDStatus.INBOX,
            priority=Priority.NORMAL,
        )

    def _create_document(self, filename="file.pdf", content=b"data"):
        from django.core.files.base import ContentFile

        doc = Document(
            item=self.item,
            file_name=filename,
            file_size=len(content),
            content_type="application/pdf",
            user=self.user,
        )
        doc.file.save(filename, ContentFile(content), save=True)
        return doc

    def test_deleting_item_removes_document_files(self):
        """Physical files must be deleted when the parent Item is deleted."""
        doc = self._create_document()
        file_name = doc.file.name
        storage = doc.file.storage

        self.assertTrue(storage.exists(file_name))

        self.item.delete()

        self.assertEqual(Document.objects.filter(id=doc.id).count(), 0)
        self.assertFalse(storage.exists(file_name))

    def test_deleting_item_removes_multiple_document_files(self):
        """All physical files are removed when an Item with multiple docs is deleted."""
        doc1 = self._create_document("a.pdf", b"aaa")
        doc2 = self._create_document("b.pdf", b"bbb")
        storage = doc1.file.storage
        file1, file2 = doc1.file.name, doc2.file.name

        self.item.delete()

        self.assertFalse(storage.exists(file1))
        self.assertFalse(storage.exists(file2))
