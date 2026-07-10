"""Local SMTP engine built on aiosmtpd.

The SMTP conversation runs on the aiosmtpd event loop; all database work is
funneled through sync_to_async(thread_sensitive=True) so the Django ORM runs
on a single dedicated worker thread with one connection.
"""

import logging
import signal
import threading

from aiosmtpd.controller import Controller
from asgiref.sync import sync_to_async

from task_processor.mail_inbox import pipeline
from task_processor.mail_inbox.rate_limit import RateLimiter

from . import BaseEngine

logger = logging.getLogger("task_processor.mail_inbox")


class InboxSMTPHandler:
    """aiosmtpd handler. Dependencies are injectable for tests."""

    def __init__(self, resolve=None, ingest=None, limiter=None):
        limiter = limiter or RateLimiter()
        self._resolve = sync_to_async(
            resolve or pipeline.resolve_recipient, thread_sensitive=True
        )
        self._ingest = sync_to_async(
            ingest or pipeline.ingest_message, thread_sensitive=True
        )
        self._limiter_hit = sync_to_async(limiter.hit, thread_sensitive=True)

    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        mail_from = envelope.mail_from or ""
        # Throttle by sender before revealing anything about the recipient,
        # so bulk probing hits 450 regardless of address validity.
        if await self._limiter_hit(mail_from):
            logger.info("Throttled sender=%s", mail_from)
            return pipeline.RETRY_LATER

        inbox, reason = await self._resolve(mail_from, address)
        if inbox is None:
            logger.info(
                "Rejected RCPT from=%s to=%s reason=%s",
                mail_from,
                address,
                reason.value,
            )
            return pipeline.REJECT_RCPT

        if await self._limiter_hit(mail_from, inbox.pk):
            logger.info("Throttled from=%s to=%s", mail_from, address)
            return pipeline.RETRY_LATER

        envelope.rcpt_tos.append(address)
        return "250 OK"

    async def handle_DATA(self, server, session, envelope):
        for rcpt in envelope.rcpt_tos:
            result = await self._ingest(
                envelope.original_content, envelope.mail_from or "", rcpt
            )
            if not result.accepted:
                return result.smtp_message
        return pipeline.ACCEPTED


class SmtpEngine(BaseEngine):
    def __init__(self, host, port, data_size_limit):
        self.host = host
        self.port = port
        self.data_size_limit = data_size_limit
        self._stop_event = threading.Event()

    def run(self):
        controller = Controller(
            InboxSMTPHandler(),
            hostname=self.host,
            port=self.port,
            data_size_limit=self.data_size_limit,
            ident="tasks-manager mail inbox",
        )
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, lambda *_: self.stop())
        controller.start()
        logger.info("SMTP inbox listening on %s:%d", self.host, self.port)
        try:
            self._stop_event.wait()
        finally:
            controller.stop()
            logger.info("SMTP inbox stopped")

    def stop(self):
        self._stop_event.set()
