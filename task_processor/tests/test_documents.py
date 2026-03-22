import io
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

        pdf_content = b"fake pdf content"
        pdf_file = io.BytesIO(pdf_content)
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

        pdf1 = io.BytesIO(b"pdf 1")
        pdf1.name = "test1.pdf"
        pdf2 = io.BytesIO(b"pdf 2")
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

        pdf_file = io.BytesIO(b"pdf content")
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
