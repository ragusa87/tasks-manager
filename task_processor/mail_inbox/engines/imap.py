"""Remote IMAP polling engine.

Connects to a mailbox on an IMAP server (optionally over TLS), fetches unseen
messages on a fixed interval and pushes each one through the shared ingestion
pipeline. It reuses ``pipeline.resolve_recipient`` / ``pipeline.ingest_message``
unchanged, so an IMAP-delivered message becomes a task exactly like an
SMTP-delivered one.

Unlike the SMTP engine there is no event loop: this runs synchronously in the
management command thread and talks to the Django ORM directly.

The per-inbox policy is enforced by ``pipeline.resolve_recipient``: a message is
only turned into a task if the inbox is enabled ("Accept incoming email") *and*
the sender is whitelisted ("trusted senders"). Anything else is dropped.

Design notes:
- Every message we handle is **deleted** from the mailbox (flagged ``\\Deleted``
  then expunged) so the account never fills up. This applies whether the mail
  was delivered as a task, dropped because the inbox is disabled, or dropped
  because the sender is not trusted — each outcome is logged with its reason.
- Messages are peeked (``BODY.PEEK[]``) so a crash mid-ingest does not consume
  the message; deletion happens only after successful processing.
- A transient/internal ingestion failure leaves the message in place so the
  next poll retries it.
- In dry-run mode (``?dry_run=1``) the engine is read-only: it logs what it
  would do with each message but creates no tasks and deletes no mail — useful
  to point at a live account and watch the log before it starts consuming it.
"""

import imaplib
import logging
import signal
import ssl
import threading
from email import message_from_bytes, policy
from email.utils import getaddresses

from task_processor.mail_inbox import pipeline
from task_processor.mail_inbox.pipeline import RejectReason

from . import BaseEngine

logger = logging.getLogger("task_processor.mail_inbox")

# Headers scanned for the delivery address, most authoritative first.
RECIPIENT_HEADERS = ("Delivered-To", "X-Original-To", "To", "Cc")


def candidate_recipients(message, headers=RECIPIENT_HEADERS):
    """Return the de-duplicated recipient addresses found in ``message``."""
    raw = []
    for name in headers:
        raw.extend(message.get_all(name, []))
    seen = set()
    recipients = []
    for _, addr in getaddresses(raw):
        addr = addr.strip()
        key = addr.lower()
        if addr and key not in seen:
            seen.add(key)
            recipients.append(addr)
    return recipients


class ImapEngine(BaseEngine):
    def __init__(
        self,
        host,
        port,
        username,
        password,
        mailbox="INBOX",
        poll_interval=60,
        use_ssl=True,
        dry_run=False,
        client_factory=None,
        resolve=None,
        ingest=None,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.mailbox = mailbox
        self.poll_interval = poll_interval
        self.use_ssl = use_ssl
        self.dry_run = dry_run
        self._client_factory = client_factory or self._connect
        self._resolve = resolve or pipeline.resolve_recipient
        self._ingest = ingest or pipeline.ingest_message
        self._stop_event = threading.Event()

    def _connect(self):
        if self.use_ssl:
            client = imaplib.IMAP4_SSL(
                self.host, self.port, ssl_context=ssl.create_default_context()
            )
        else:
            client = imaplib.IMAP4(self.host, self.port)
        client.login(self.username, self.password)
        return client

    def process_message(self, raw):
        """Process one raw RFC822 message and decide its fate in the mailbox.

        Returns True if the message may be deleted — either delivered as a task,
        or dropped because of the inbox policy (disabled inbox / untrusted
        sender) or because it is unrelated to any inbox. Returns False only on a
        transient/internal failure, so it stays and is retried next poll.

        In dry-run mode nothing is written: recipients are resolved and the
        intended action is logged, but no task is created (``ingest`` is not
        called). The mailbox is left untouched by ``poll_once``.
        """
        dry = self.dry_run
        verb = "would delete (dry-run)" if dry else "deleting"
        message = message_from_bytes(raw, policy=policy.default)
        mail_from = str(message.get("From", ""))
        sender = pipeline._addr_spec(mail_from)
        transient = False
        handled = False
        for rcpt in candidate_recipients(message):
            to = pipeline._addr_spec(rcpt)
            inbox, reason = self._resolve(mail_from, rcpt)
            if inbox is None:
                # A real inbox refused this mail (disabled / untrusted sender);
                # log it. Mail simply not addressed to us stays at debug.
                if reason == RejectReason.UNKNOWN_RECIPIENT:
                    logger.debug("Ignoring recipient to=%s (unknown)", to)
                else:
                    handled = True
                    logger.info(
                        "Dropping mail from=%s to=%s reason=%s; %s",
                        sender,
                        to,
                        reason.value,
                        verb,
                    )
                continue
            if dry:
                handled = True
                logger.info(
                    "Would deliver mail from=%s to=%s; dry-run, no task created",
                    sender,
                    to,
                )
                continue
            result = self._ingest(raw, mail_from, rcpt)
            if result.accepted:
                handled = True
                logger.info(
                    "Delivered mail from=%s to=%s item=%s; %s",
                    sender,
                    to,
                    getattr(result.item, "pk", None),
                    verb,
                )
            elif result.reason == RejectReason.INTERNAL:
                transient = True
            else:
                handled = True
                logger.info(
                    "Dropping mail from=%s to=%s reason=%s; %s",
                    sender,
                    to,
                    result.reason.value if result.reason else "unknown",
                    verb,
                )
        if not handled and not transient:
            logger.info("Dropping unrelated mail from=%s; %s", sender, verb)
        return not transient

    def poll_once(self, client):
        """Fetch and process every message in the mailbox, deleting those handled.

        In dry-run mode messages are processed and logged but never flagged or
        expunged, so the mailbox is left exactly as found.
        """
        client.select(self.mailbox)
        typ, data = client.search(None, "ALL")
        if typ != "OK":
            logger.warning("IMAP search failed: %s", typ)
            return
        deleted = 0
        for num in data[0].split():
            if self._stop_event.is_set():
                break
            typ, msg_data = client.fetch(num, "(BODY.PEEK[])")
            if typ != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
                logger.warning("IMAP fetch failed for message %r", num)
                continue
            raw = msg_data[0][1]
            if self.process_message(raw) and not self.dry_run:
                client.store(num, "+FLAGS", "\\Deleted")
                deleted += 1
        # Expunge once, after the loop, so sequence numbers stay stable while we
        # iterate the messages we searched.
        if deleted:
            client.expunge()

    def run(self):
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, lambda *_: self.stop())
        logger.info(
            "IMAP inbox polling %s:%d mailbox=%s every %ds",
            self.host,
            self.port,
            self.mailbox,
            self.poll_interval,
        )
        while not self._stop_event.is_set():
            client = None
            try:
                client = self._client_factory()
                self.poll_once(client)
            except Exception:
                logger.exception("IMAP poll cycle failed; will retry")
            finally:
                if client is not None:
                    try:
                        client.logout()
                    except Exception:
                        logger.debug("IMAP logout failed", exc_info=True)
            self._stop_event.wait(self.poll_interval)
        logger.info("IMAP inbox stopped")

    def stop(self):
        self._stop_event.set()
