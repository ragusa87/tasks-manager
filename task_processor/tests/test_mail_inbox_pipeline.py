from email.message import EmailMessage

from django.contrib.auth.models import Permission, User
from django.test import TestCase, override_settings

from task_processor.constants import GTDStatus
from task_processor.mail_inbox import pipeline
from task_processor.mail_inbox.pipeline import (
    REJECT_RCPT,
    RejectReason,
    ingest_message,
    resolve_recipient,
)
from task_processor.models import AllowedSender, Document, EmailInbox, Item

DOMAIN = "tasks.example.com"

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x00IEND\xaeB`\x82"
)
MP3_BYTES = b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00" * 64
ZIP_BYTES = b"PK\x03\x04" + b"\x00" * 64


def build_raw(
    subject="Test subject",
    body="Test body",
    html=None,
    sender="sender@example.com",
    to=f"inbox-abc@{DOMAIN}",
    attachments=(),
):
    message = EmailMessage()
    message["From"] = sender
    message["To"] = to
    if subject is not None:
        message["Subject"] = subject
    if body is not None:
        message.set_content(body)
    if html is not None:
        if body is not None:
            message.add_alternative(html, subtype="html")
        else:
            message.set_content(html, subtype="html")
    for name, data, maintype, subtype in attachments:
        message.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
    return bytes(message)


@override_settings(USER_EMAIL_INBOX_DOMAIN=DOMAIN)
class MailInboxPipelineTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        self.grant_permission(self.user)
        self.inbox = EmailInbox.objects.create(user=self.user, identifier="inbox-abc")
        AllowedSender.objects.create(inbox=self.inbox, email="sender@example.com")

    def grant_permission(self, user):
        user.user_permissions.add(
            Permission.objects.get(
                codename="use_email_inbox",
                content_type__app_label="task_processor",
            )
        )


class ResolveRecipientTests(MailInboxPipelineTestCase):
    def assert_rejected(self, mail_from, rcpt_to, expected_reason):
        inbox, reason = resolve_recipient(mail_from, rcpt_to)
        self.assertIsNone(inbox)
        self.assertEqual(reason, expected_reason)

    def test_accepts_valid_envelope(self):
        inbox, reason = resolve_recipient("sender@example.com", f"inbox-abc@{DOMAIN}")
        self.assertEqual(inbox, self.inbox)
        self.assertIsNone(reason)

    def test_accepts_display_name_and_case(self):
        inbox, _ = resolve_recipient(
            "Some One <SENDER@Example.COM>", f"Inbox-ABC@{DOMAIN.upper()}"
        )
        self.assertEqual(inbox, self.inbox)

    def test_rejects_wrong_domain(self):
        self.assert_rejected(
            "sender@example.com",
            "inbox-abc@evil.example.org",
            RejectReason.UNKNOWN_RECIPIENT,
        )

    def test_rejects_unknown_local_part(self):
        self.assert_rejected(
            "sender@example.com",
            f"inbox-nope@{DOMAIN}",
            RejectReason.UNKNOWN_RECIPIENT,
        )

    def test_rejects_disabled_inbox(self):
        self.inbox.enabled = False
        self.inbox.save()
        self.assert_rejected(
            "sender@example.com", f"inbox-abc@{DOMAIN}", RejectReason.DISABLED
        )

    def test_rejects_inactive_user(self):
        self.user.is_active = False
        self.user.save()
        self.assert_rejected(
            "sender@example.com", f"inbox-abc@{DOMAIN}", RejectReason.DISABLED
        )

    def test_rejects_user_without_permission(self):
        self.user.user_permissions.clear()
        self.assert_rejected(
            "sender@example.com", f"inbox-abc@{DOMAIN}", RejectReason.NOT_PERMITTED
        )

    def test_rejects_non_whitelisted_sender(self):
        self.assert_rejected(
            "stranger@example.com",
            f"inbox-abc@{DOMAIN}",
            RejectReason.SENDER_NOT_ALLOWED,
        )

    def test_all_rejections_yield_the_same_smtp_reply(self):
        """Anti-enumeration: a prober must not learn WHY a mail was refused."""
        cases = [
            ("sender@example.com", f"inbox-nope@{DOMAIN}"),  # unknown recipient
            ("stranger@example.com", f"inbox-abc@{DOMAIN}"),  # not whitelisted
        ]
        self.inbox.enabled = False
        self.inbox.save()
        cases.append(("sender@example.com", f"inbox-abc@{DOMAIN}"))  # disabled

        replies = set()
        for mail_from, rcpt_to in cases:
            result = ingest_message(build_raw(), mail_from, rcpt_to)
            self.assertFalse(result.accepted)
            replies.add(result.smtp_message)
        self.assertEqual(replies, {REJECT_RCPT})


class IngestMessageTests(MailInboxPipelineTestCase):
    def ingest(self, raw):
        return ingest_message(raw, "sender@example.com", f"inbox-abc@{DOMAIN}")

    def test_creates_inbox_item(self):
        result = self.ingest(build_raw(subject="Buy milk", body="2 liters"))
        self.assertTrue(result.accepted)
        item = Item.objects.get(user=self.user)
        self.assertEqual(item.title, "Buy milk")
        self.assertEqual(item.status, GTDStatus.INBOX)
        self.assertIn("2 liters", item.description)
        self.assertIn("Received by email from sender@example.com", item.description)

    def test_encoded_subject_is_decoded(self):
        result = self.ingest(build_raw(subject="Café résumé ✓"))
        self.assertEqual(result.item.title, "Café résumé ✓")

    def test_overlong_subject_is_truncated(self):
        result = self.ingest(build_raw(subject="x" * 3000))
        self.assertEqual(len(result.item.title), 1024)

    def test_missing_subject_gets_fallback(self):
        result = self.ingest(build_raw(subject=None))
        self.assertEqual(result.item.title, pipeline.NO_SUBJECT)

    def test_html_only_body_is_stripped(self):
        raw = build_raw(
            body=None,
            html="<html><style>p{}</style><body><p>Hello</p><p>World</p></body></html>",
        )
        result = self.ingest(raw)
        self.assertIn("Hello\nWorld", result.item.description)
        self.assertNotIn("<p>", result.item.description)

    def test_multipart_prefers_plain_text(self):
        raw = build_raw(body="plain wins", html="<p>html loses</p>")
        result = self.ingest(raw)
        self.assertIn("plain wins", result.item.description)
        self.assertNotIn("html loses", result.item.description)

    def test_pdf_attachment_saved_as_document(self):
        raw = build_raw(attachments=[("report.pdf", PDF_BYTES, "application", "pdf")])
        result = self.ingest(raw)
        document = Document.objects.get(item=result.item)
        self.assertEqual(document.file_name, "report.pdf")
        self.assertEqual(document.content_type, "application/pdf")
        self.assertEqual(document.file_size, len(PDF_BYTES))
        with document.file.open("rb") as fh:
            self.assertEqual(fh.read(), PDF_BYTES)
        document.delete()

    def test_attachment_with_oversized_filename_still_saved(self):
        # The filename is attacker-controlled; a huge "extension" must not
        # overflow the FileField max_length and 451 the whole message.
        name = "report." + "a" * 600
        raw = build_raw(attachments=[(name, PDF_BYTES, "application", "pdf")])
        result = self.ingest(raw)
        self.assertTrue(result.accepted)
        document = Document.objects.get(item=result.item)
        self.assertEqual(document.file_name, name[:255])
        self.assertLessEqual(
            len(document.file.name), Document._meta.get_field("file").max_length
        )
        document.delete()

    def test_image_and_audio_attachments_allowed(self):
        raw = build_raw(
            attachments=[
                ("photo.png", PNG_BYTES, "image", "png"),
                ("note.mp3", MP3_BYTES, "audio", "mpeg"),
            ]
        )
        result = self.ingest(raw)
        types = set(
            Document.objects.filter(item=result.item).values_list(
                "content_type", flat=True
            )
        )
        self.assertEqual(types, {"image/png", "audio/mpeg"})
        for document in Document.objects.filter(item=result.item):
            document.delete()

    def test_disallowed_attachment_skipped_with_note(self):
        raw = build_raw(attachments=[("archive.zip", ZIP_BYTES, "application", "zip")])
        result = self.ingest(raw)
        self.assertTrue(result.accepted)
        self.assertEqual(Document.objects.filter(item=result.item).count(), 0)
        self.assertEqual(len(result.skipped_attachments), 1)
        self.assertIn("archive.zip", result.item.description)
        self.assertIn("not allowed", result.item.description)

    @override_settings(EMAIL_INBOX_ATTACHMENT_MAX_SIZE=10)
    def test_oversize_attachment_skipped(self):
        raw = build_raw(attachments=[("report.pdf", PDF_BYTES, "application", "pdf")])
        result = self.ingest(raw)
        self.assertEqual(Document.objects.filter(item=result.item).count(), 0)
        self.assertIn("exceeds", result.item.description)

    @override_settings(EMAIL_INBOX_MAX_ATTACHMENTS=1)
    def test_attachment_count_limit(self):
        raw = build_raw(
            attachments=[
                ("a.pdf", PDF_BYTES, "application", "pdf"),
                ("b.pdf", PDF_BYTES, "application", "pdf"),
            ]
        )
        result = self.ingest(raw)
        self.assertEqual(Document.objects.filter(item=result.item).count(), 1)
        self.assertEqual(len(result.skipped_attachments), 1)
        for document in Document.objects.filter(item=result.item):
            document.delete()

    def test_malformed_message_still_creates_item(self):
        # email.message_from_bytes is extremely lenient: garbage becomes an
        # empty message rather than an exception, so ingest falls back.
        result = self.ingest(b"\xff\xfe not an email at all")
        self.assertTrue(result.accepted)
        self.assertEqual(result.item.title, pipeline.NO_SUBJECT)
