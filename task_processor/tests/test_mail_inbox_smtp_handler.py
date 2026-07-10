import asyncio
from types import SimpleNamespace

from django.test import SimpleTestCase

from task_processor.mail_inbox import pipeline
from task_processor.mail_inbox.engines.smtp import InboxSMTPHandler
from task_processor.mail_inbox.pipeline import IngestResult, RejectReason


class FakeLimiter:
    def __init__(self, exceeded=False):
        self.exceeded = exceeded
        self.calls = []

    def hit(self, sender, inbox_id=None):
        self.calls.append((sender, inbox_id))
        return self.exceeded


def make_envelope(mail_from="sender@example.com"):
    return SimpleNamespace(
        mail_from=mail_from, rcpt_tos=[], original_content=b"raw message"
    )


def resolve_ok(mail_from, rcpt_to):
    return SimpleNamespace(pk=1), None


def resolve_reject(mail_from, rcpt_to):
    return None, RejectReason.UNKNOWN_RECIPIENT


class HandleRCPTTests(SimpleTestCase):
    def rcpt(self, handler, envelope, address="inbox-abc@tasks.example.com"):
        return asyncio.run(handler.handle_RCPT(None, None, envelope, address, []))

    def test_valid_recipient_accepted(self):
        envelope = make_envelope()
        handler = InboxSMTPHandler(resolve=resolve_ok, limiter=FakeLimiter())
        reply = self.rcpt(handler, envelope)
        self.assertEqual(reply, "250 OK")
        self.assertEqual(envelope.rcpt_tos, ["inbox-abc@tasks.example.com"])

    def test_rejected_recipient_gets_generic_550(self):
        envelope = make_envelope()
        handler = InboxSMTPHandler(resolve=resolve_reject, limiter=FakeLimiter())
        reply = self.rcpt(handler, envelope)
        self.assertEqual(reply, pipeline.REJECT_RCPT)
        self.assertEqual(envelope.rcpt_tos, [])

    def test_throttled_sender_gets_450_before_resolution(self):
        calls = []

        def resolve_should_not_run(mail_from, rcpt_to):
            calls.append(rcpt_to)
            return resolve_ok(mail_from, rcpt_to)

        handler = InboxSMTPHandler(
            resolve=resolve_should_not_run, limiter=FakeLimiter(exceeded=True)
        )
        reply = self.rcpt(handler, make_envelope())
        self.assertEqual(reply, pipeline.RETRY_LATER)
        self.assertEqual(calls, [])

    def test_limiter_called_per_sender_then_per_recipient(self):
        limiter = FakeLimiter()
        handler = InboxSMTPHandler(resolve=resolve_ok, limiter=limiter)
        self.rcpt(handler, make_envelope())
        self.assertEqual(
            limiter.calls,
            [("sender@example.com", None), ("sender@example.com", 1)],
        )


class HandleDATATests(SimpleTestCase):
    def data(self, handler, envelope):
        return asyncio.run(handler.handle_DATA(None, None, envelope))

    def test_accepted_message(self):
        def ingest(raw, mail_from, rcpt_to):
            return IngestResult(accepted=True, smtp_message=pipeline.ACCEPTED)

        envelope = make_envelope()
        envelope.rcpt_tos = ["inbox-abc@tasks.example.com"]
        handler = InboxSMTPHandler(
            resolve=resolve_ok, ingest=ingest, limiter=FakeLimiter()
        )
        self.assertEqual(self.data(handler, envelope), pipeline.ACCEPTED)

    def test_rejected_message_propagates_reply(self):
        def ingest(raw, mail_from, rcpt_to):
            return IngestResult(
                accepted=False,
                smtp_message=pipeline.REJECT_RCPT,
                reason=RejectReason.DISABLED,
            )

        envelope = make_envelope()
        envelope.rcpt_tos = ["inbox-abc@tasks.example.com"]
        handler = InboxSMTPHandler(
            resolve=resolve_ok, ingest=ingest, limiter=FakeLimiter()
        )
        self.assertEqual(self.data(handler, envelope), pipeline.REJECT_RCPT)
