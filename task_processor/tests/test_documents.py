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
    # Embed the payload as a trailing comment so different `content` values
    # produce different bytes (needed by the duplicate-detection tests).
    return body + b"% " + content + b"\n"


def make_png() -> bytes:
    """Return a minimal 1x1 PNG that python-magic recognises as image/png."""
    import struct
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data))
        )

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)  # 1x1, 8-bit grayscale
    idat = zlib.compress(b"\x00\x00")  # one scanline: filter byte + pixel
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", idat)
        + chunk(b"IEND", b"")
    )


def make_wav() -> bytes:
    """Return a minimal WAV header that python-magic recognises as audio."""
    import struct

    fmt = struct.pack("<HHIIHH", 1, 1, 8000, 8000, 1, 8)  # PCM mono 8kHz 8-bit
    data = b"\x80" * 8  # 1ms of silence
    body = (
        b"WAVE"
        + b"fmt "
        + struct.pack("<I", len(fmt))
        + fmt
        + b"data"
        + struct.pack("<I", len(data))
        + data
    )
    return b"RIFF" + struct.pack("<I", len(body)) + body


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

        pdf1 = io.BytesIO(make_pdf(b"first file"))
        pdf1.name = "test1.pdf"
        pdf2 = io.BytesIO(make_pdf(b"second file"))
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

    def test_upload_png_success(self):
        """Images are accepted and stored with their sniffed content type."""
        self.client.force_login(self.user)

        png_file = io.BytesIO(make_png())
        png_file.name = "photo.png"

        response = self.client.post(
            reverse("document_upload", args=[self.item.id]),
            {"files": png_file},
        )

        self.assertEqual(response.status_code, 200)
        document = Document.objects.get()
        self.assertEqual(document.content_type, "image/png")
        self.assertEqual(document.icon, "lucide-image")

    def test_upload_wav_success(self):
        """Audio files are accepted and stored with their sniffed content type."""
        self.client.force_login(self.user)

        wav_file = io.BytesIO(make_wav())
        wav_file.name = "note.wav"

        response = self.client.post(
            reverse("document_upload", args=[self.item.id]),
            {"files": wav_file},
        )

        self.assertEqual(response.status_code, 200)
        document = Document.objects.get()
        self.assertTrue(document.content_type.startswith("audio/"))
        self.assertEqual(document.icon, "lucide-music")

    def test_upload_disallowed_type_rejected(self):
        """Types outside the allow-list are rejected by magic-byte detection,
        even with an allowed extension and Content-Type."""
        self.client.force_login(self.user)

        text_file = io.BytesIO(b"#!/bin/sh\necho hello\n")
        text_file.name = "script.pdf"  # lying extension

        response = self.client.post(
            reverse("document_upload", args=[self.item.id]),
            {"files": text_file},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Document.objects.count(), 0)
        self.assertContains(response, "file type not allowed")

    def test_upload_duplicate_content_rejected(self):
        """Re-uploading identical content is refused even under another name."""
        self.client.force_login(self.user)

        first = io.BytesIO(make_pdf())
        first.name = "report.pdf"
        self.client.post(
            reverse("document_upload", args=[self.item.id]), {"files": first}
        )

        again = io.BytesIO(make_pdf())
        again.name = "renamed-copy.pdf"
        response = self.client.post(
            reverse("document_upload", args=[self.item.id]), {"files": again}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Document.objects.count(), 1)
        self.assertContains(response, "identical file already attached")

    def test_upload_duplicate_within_batch_rejected(self):
        """Two identical files in one multi-upload store only one document."""
        self.client.force_login(self.user)

        copy1 = io.BytesIO(make_pdf())
        copy1.name = "a.pdf"
        copy2 = io.BytesIO(make_pdf())
        copy2.name = "b.pdf"
        response = self.client.post(
            reverse("document_upload", args=[self.item.id]),
            {"files": [copy1, copy2]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Document.objects.count(), 1)
        self.assertContains(response, "identical file already attached")

    def test_same_content_allowed_on_other_item(self):
        """Dedup is per item: another task may attach the same file."""
        self.client.force_login(self.user)
        other_item = Item.objects.create(
            title="Other own item",
            status=GTDStatus.INBOX,
            priority=Priority.NORMAL,
            user=self.user,
        )

        for target in (self.item, other_item):
            pdf = io.BytesIO(make_pdf())
            pdf.name = "same.pdf"
            self.client.post(
                reverse("document_upload", args=[target.id]), {"files": pdf}
            )

        self.assertEqual(Document.objects.count(), 2)

    def test_content_hash_populated_on_save(self):
        """Document.save() hashes the file, so all creation paths get a hash."""
        import hashlib

        content = make_pdf()
        pdf = io.BytesIO(content)
        pdf.name = "hashed.pdf"
        self.client.force_login(self.user)
        self.client.post(
            reverse("document_upload", args=[self.item.id]), {"files": pdf}
        )

        document = Document.objects.get()
        self.assertEqual(document.content_hash, hashlib.sha256(content).hexdigest())

    def test_document_icon_per_content_type(self):
        """The icon property maps content types to sprite names."""
        cases = [
            ("application/pdf", "lucide-file"),
            ("image/jpeg", "lucide-image"),
            ("audio/mpeg", "lucide-music"),
            ("", "lucide-file"),
        ]
        for content_type, expected in cases:
            with self.subTest(content_type=content_type):
                document = Document(content_type=content_type)
                self.assertEqual(document.icon, expected)


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


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)
class DocumentAudioPreviewTests(TestCase):
    """Audio rows in the document list render an in-browser preview
    (play button + lazy <audio> element); other types don't."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        self.client.force_login(self.user)
        self.item = Item.objects.create(
            title="Test item",
            status=GTDStatus.INBOX,
            priority=Priority.NORMAL,
            user=self.user,
        )

    def _upload(self, name, payload):
        file = io.BytesIO(payload)
        file.name = name
        return self.client.post(
            reverse("document_upload", args=[self.item.id]),
            {"files": file},
        )

    def test_is_audio_property(self):
        document = Document(content_type="audio/x-wav")
        self.assertTrue(document.is_audio)
        self.assertFalse(Document(content_type="application/pdf").is_audio)
        self.assertFalse(Document(content_type="image/png").is_audio)

    def test_audio_row_renders_preview(self):
        response = self._upload("note.wav", make_wav())
        self.assertEqual(response.status_code, 200)
        document = Document.objects.get()
        self.assertContains(response, "audio-preview-btn")
        self.assertContains(
            response,
            f'data-audio-url="{reverse("document_download", args=[document.id])}"',
        )
        # Player is present but lazy: hidden, preload="none" and no src yet.
        self.assertContains(response, 'preload="none"')
        self.assertNotContains(response, "<audio controls src=")

    def test_non_audio_row_has_no_preview(self):
        response = self._upload("doc.pdf", make_pdf())
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "audio-preview-btn")
        self.assertNotContains(response, "<audio")
