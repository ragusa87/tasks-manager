"""Engine-agnostic ingestion of a received email into a task.

The entry points are pure sync functions taking primitive values (raw bytes,
envelope addresses), so any engine (local SMTP server, future IMAP poller,
Celery task) can reuse them unchanged.

Security notes:
- Every permanent rejection maps to the same SMTP reply (REJECT_RCPT) so a
  prober cannot distinguish a nonexistent inbox from a disabled one or from a
  non-whitelisted sender. The precise reason is only logged server-side.
- Message content (subject, body, attachment names) is never logged.
"""

import enum
import logging
import posixpath
from dataclasses import dataclass, field
from email import message_from_bytes, policy
from email.utils import parseaddr
from html.parser import HTMLParser

import magic
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import close_old_connections, transaction

from task_processor.models import Document, EmailInbox, Item
from task_processor.models.email_inbox import EMAIL_INBOX_PERMISSION

logger = logging.getLogger("task_processor.mail_inbox")

REJECT_RCPT = "550 5.7.1 Recipient address rejected"
RETRY_LATER = "450 4.7.1 Rate limit exceeded, try again later"
ACCEPTED = "250 Message accepted for delivery"
INTERNAL_ERROR = "451 4.3.0 Temporary internal failure, try again later"

TITLE_MAX_LENGTH = 1024
NO_SUBJECT = "(no subject)"


class RejectReason(enum.Enum):
    UNKNOWN_RECIPIENT = "unknown_recipient"
    DISABLED = "disabled"
    NOT_PERMITTED = "not_permitted"
    SENDER_NOT_ALLOWED = "sender_not_allowed"
    RATE_LIMITED = "rate_limited"
    PARSE_ERROR = "parse_error"
    INTERNAL = "internal"


@dataclass
class IngestResult:
    accepted: bool
    smtp_message: str
    reason: RejectReason | None = None
    item: object = None
    skipped_attachments: list = field(default_factory=list)


def _addr_spec(value):
    return parseaddr(value or "")[1].strip().lower()


def _upload_name(name):
    """Cap the attacker-controlled filename handed to upload_to.

    Only the extension survives into the storage path, but an oversized one
    would overflow the FileField max_length and turn the whole message into
    a 451. Document.file_name keeps the original (truncated) name.
    """
    stem, ext = posixpath.splitext(name)
    return f"{stem[:64] or 'attachment'}{ext[:16]}"


def resolve_recipient(mail_from, rcpt_to):
    """Return (EmailInbox, None) if this envelope may deliver, else (None, reason)."""
    sender = _addr_spec(mail_from)
    recipient = _addr_spec(rcpt_to)
    if "@" not in recipient:
        return None, RejectReason.UNKNOWN_RECIPIENT
    local_part, domain = recipient.rsplit("@", 1)
    if domain != settings.USER_EMAIL_INBOX_DOMAIN.lower():
        return None, RejectReason.UNKNOWN_RECIPIENT

    inbox = EmailInbox.resolve(local_part)
    if inbox is None:
        return None, RejectReason.UNKNOWN_RECIPIENT
    if not inbox.enabled or not inbox.user.is_active:
        return None, RejectReason.DISABLED
    if not inbox.user.has_perm(EMAIL_INBOX_PERMISSION):
        return None, RejectReason.NOT_PERMITTED
    if not sender or not inbox.is_sender_allowed(sender):
        return None, RejectReason.SENDER_NOT_ALLOWED
    return inbox, None


class _HTMLTextExtractor(HTMLParser):
    SKIP_TAGS = {"script", "style", "head"}
    BREAK_TAGS = {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__()
        self._chunks = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
        elif tag in self.BREAK_TAGS:
            self._chunks.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if not self._skip_depth:
            self._chunks.append(data)

    def text(self):
        lines = [line.strip() for line in "".join(self._chunks).splitlines()]
        return "\n".join(line for line in lines if line)


def html_to_text(html):
    extractor = _HTMLTextExtractor()
    extractor.feed(html)
    return extractor.text()


def extract_subject(message):
    subject = " ".join(str(message.get("Subject", "")).split()).strip()
    return (subject or NO_SUBJECT)[:TITLE_MAX_LENGTH]


def extract_body(message):
    part = message.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    try:
        content = part.get_content()
    except (LookupError, UnicodeError):
        return ""
    if part.get_content_type() == "text/html":
        return html_to_text(content)
    return content.strip()


def extract_attachments(message):
    """Return (kept, notes): decoded attachments passing the allowlist, and
    human-readable notes about the ones that were skipped."""
    # Uploads switched off on this instance (e.g. locked-down demo): still file
    # the message, but drop every attachment and note each so the item records
    # what was skipped.
    if not settings.ALLOW_FILES_UPLOAD:
        notes = [
            f"{part.get_filename() or 'attachment'}: skipped, uploads are disabled"
            for part in message.iter_attachments()
        ]
        return [], notes

    max_count = settings.EMAIL_INBOX_MAX_ATTACHMENTS
    max_size = settings.EMAIL_INBOX_ATTACHMENT_MAX_SIZE
    allowed_types = settings.EMAIL_INBOX_ATTACHMENT_ALLOWED_TYPES

    kept = []
    notes = []
    for part in message.iter_attachments():
        name = part.get_filename() or "attachment"
        if len(kept) >= max_count:
            notes.append(f"{name}: skipped, more than {max_count} attachments")
            continue
        try:
            data = part.get_content()
        except (LookupError, UnicodeError):
            notes.append(f"{name}: skipped, could not decode")
            continue
        if isinstance(data, str):
            data = data.encode("utf-8")
        if not isinstance(data, bytes):
            notes.append(f"{name}: skipped, unsupported content")
            continue
        if len(data) > max_size:
            notes.append(
                f"{name}: skipped, exceeds the {max_size // (1024 * 1024)} MB limit"
            )
            continue
        # Sniff the real type from the bytes, never trust the declared one.
        detected_type = magic.from_buffer(data[:2048], mime=True)
        if detected_type not in allowed_types:
            notes.append(f"{name}: skipped, file type {detected_type} not allowed")
            continue
        kept.append((name, data, detected_type))
    return kept, notes


def ingest_message(raw, mail_from, rcpt_to):
    """Turn a raw RFC822 message into an inbox Item for the resolved user."""
    close_old_connections()

    # Re-check: DB state may have changed between RCPT acceptance and DATA.
    inbox, reason = resolve_recipient(mail_from, rcpt_to)
    if inbox is None:
        logger.info(
            "Rejected message from=%s to=%s reason=%s", mail_from, rcpt_to, reason.value
        )
        return IngestResult(accepted=False, smtp_message=REJECT_RCPT, reason=reason)

    try:
        message = message_from_bytes(raw, policy=policy.default)
        title = extract_subject(message)
        body = extract_body(message)
        attachments, skipped = extract_attachments(message)

        description = body.strip()
        footer = [f"Received by email from {_addr_spec(mail_from)}"]
        footer += [f"Attachment {note}" for note in skipped]
        description += ("\n\n---\n" if description else "") + "\n".join(footer)

        with transaction.atomic():
            item = Item.objects.create(
                title=title, description=description, user=inbox.user
            )
            for name, data, content_type in attachments:
                Document.objects.create(
                    item=item,
                    user=inbox.user,
                    file=ContentFile(data, name=_upload_name(name)),
                    file_name=name[:255],
                    file_size=len(data),
                    content_type=content_type,
                )
    except Exception:
        logger.exception(
            "Failed to ingest message from=%s to=%s size=%d",
            mail_from,
            rcpt_to,
            len(raw),
        )
        return IngestResult(
            accepted=False, smtp_message=INTERNAL_ERROR, reason=RejectReason.INTERNAL
        )

    logger.info(
        "Accepted message from=%s to=%s item_id=%s attachments=%d skipped=%d",
        mail_from,
        rcpt_to,
        item.pk,
        len(attachments),
        len(skipped),
    )
    return IngestResult(
        accepted=True,
        smtp_message=ACCEPTED,
        item=item,
        skipped_attachments=skipped,
    )
