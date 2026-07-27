from email import message_from_bytes, policy
from email.message import EmailMessage

from django.contrib.auth.models import Permission, User
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from task_processor.mail_inbox.dsn import parse_dsn
from task_processor.mail_inbox.engines import build_engine
from task_processor.mail_inbox.engines.imap import ImapEngine, candidate_recipients
from task_processor.mail_inbox.pipeline import IngestResult, RejectReason
from task_processor.models import AllowedSender, EmailInbox, Item

DOMAIN = "tasks.example.com"


def build_raw(sender="sender@example.com", to=f"inbox-abc@{DOMAIN}", cc=None):
    message = EmailMessage()
    message["From"] = sender
    message["To"] = to
    if cc is not None:
        message["Cc"] = cc
    message["Subject"] = "Hello"
    message.set_content("body")
    return bytes(message)


class FakeClient:
    """Minimal stand-in for imaplib.IMAP4[_SSL]."""

    def __init__(self, messages):
        # messages: {num_bytes: raw_bytes}
        self.messages = messages
        self.selected = None
        self.stored = []
        self.expunged = 0
        self.logged_out = False

    def select(self, mailbox):
        self.selected = mailbox
        return ("OK", [b"1"])

    def search(self, charset, criteria):
        return ("OK", [b" ".join(self.messages)])

    def fetch(self, num, spec):
        return ("OK", [(b"%s (BODY[] {n}" % num, self.messages[num]), b")"])

    def store(self, num, flags, value):
        self.stored.append((num, flags, value))
        return ("OK", [b""])

    def expunge(self):
        self.expunged += 1
        return ("OK", [b""])

    def logout(self):
        self.logged_out = True


def accept_only(target):
    """Build (resolve, ingest, calls) fakes that deliver mail sent to `target`."""
    calls = []

    def resolve(mail_from, rcpt_to):
        if rcpt_to.strip().lower() == target:
            return object(), None
        return None, RejectReason.UNKNOWN_RECIPIENT

    def ingest(raw, mail_from, rcpt_to):
        calls.append(rcpt_to)
        return IngestResult(accepted=True, smtp_message="ok")

    return resolve, ingest, calls


def reject_with(reason):
    """Build (resolve, ingest, calls) fakes where a real inbox refuses the mail."""
    calls = []

    def resolve(mail_from, rcpt_to):
        return None, reason

    def ingest(raw, mail_from, rcpt_to):  # pragma: no cover - must never run
        calls.append(rcpt_to)
        return IngestResult(accepted=True, smtp_message="ok")

    return resolve, ingest, calls


class CandidateRecipientsTests(SimpleTestCase):
    def test_collects_and_dedupes_across_headers(self):
        message = message_from_bytes(
            build_raw(to="A@X.test, b@x.test", cc="A@X.test"), policy=policy.default
        )
        self.assertEqual(candidate_recipients(message), ["A@X.test", "b@x.test"])

    def test_prefers_delivered_to_first(self):
        raw = build_raw(to=f"inbox-abc@{DOMAIN}")
        raw = b"Delivered-To: real@" + DOMAIN.encode() + b"\r\n" + raw
        message = message_from_bytes(raw, policy=policy.default)
        self.assertEqual(candidate_recipients(message)[0], f"real@{DOMAIN}")


class ProcessMessageTests(SimpleTestCase):
    def _engine(self, resolve, ingest):
        return ImapEngine(
            host="h",
            port=993,
            username="u",
            password="p",
            resolve=resolve,
            ingest=ingest,
        )

    def test_delivers_to_matching_recipient(self):
        resolve, ingest, calls = accept_only(f"inbox-abc@{DOMAIN}")
        engine = self._engine(resolve, ingest)
        self.assertTrue(engine.process_message(build_raw()))
        self.assertEqual(calls, [f"inbox-abc@{DOMAIN}"])

    def test_drops_message_with_no_matching_recipient(self):
        resolve, ingest, calls = accept_only("nobody@elsewhere.test")
        engine = self._engine(resolve, ingest)
        # Returns True (delete) but never ingests.
        self.assertTrue(engine.process_message(build_raw()))
        self.assertEqual(calls, [])

    def test_drops_disabled_inbox_without_ingesting(self):
        resolve, ingest, calls = reject_with(RejectReason.DISABLED)
        engine = self._engine(resolve, ingest)
        self.assertTrue(engine.process_message(build_raw()))
        self.assertEqual(calls, [])

    def test_drops_untrusted_sender_without_ingesting(self):
        resolve, ingest, calls = reject_with(RejectReason.SENDER_NOT_ALLOWED)
        engine = self._engine(resolve, ingest)
        self.assertTrue(engine.process_message(build_raw()))
        self.assertEqual(calls, [])

    def test_transient_failure_keeps_message(self):
        def resolve(mail_from, rcpt_to):
            return object(), None

        def ingest(raw, mail_from, rcpt_to):
            return IngestResult(
                accepted=False, smtp_message="oops", reason=RejectReason.INTERNAL
            )

        engine = self._engine(resolve, ingest)
        self.assertFalse(engine.process_message(build_raw()))


class PollOnceTests(SimpleTestCase):
    def test_deletes_delivered_messages_and_expunges(self):
        resolve, ingest, calls = accept_only(f"inbox-abc@{DOMAIN}")
        engine = ImapEngine(
            host="h",
            port=993,
            username="u",
            password="p",
            mailbox="INBOX",
            resolve=resolve,
            ingest=ingest,
        )
        client = FakeClient({b"1": build_raw(), b"2": build_raw()})
        engine.poll_once(client)

        self.assertEqual(client.selected, "INBOX")
        self.assertEqual(len(calls), 2)
        self.assertEqual(
            client.stored,
            [(b"1", "+FLAGS", "\\Deleted"), (b"2", "+FLAGS", "\\Deleted")],
        )
        self.assertEqual(client.expunged, 1)

    def test_untrusted_sender_message_is_deleted(self):
        resolve, ingest, _ = reject_with(RejectReason.SENDER_NOT_ALLOWED)
        engine = ImapEngine(
            host="h",
            port=993,
            username="u",
            password="p",
            resolve=resolve,
            ingest=ingest,
        )
        client = FakeClient({b"1": build_raw()})
        engine.poll_once(client)
        self.assertEqual(client.stored, [(b"1", "+FLAGS", "\\Deleted")])
        self.assertEqual(client.expunged, 1)

    def test_transient_failure_not_deleted(self):
        def resolve(mail_from, rcpt_to):
            return object(), None

        def ingest(raw, mail_from, rcpt_to):
            return IngestResult(
                accepted=False, smtp_message="oops", reason=RejectReason.INTERNAL
            )

        engine = ImapEngine(
            host="h",
            port=993,
            username="u",
            password="p",
            resolve=resolve,
            ingest=ingest,
        )
        client = FakeClient({b"1": build_raw()})
        engine.poll_once(client)
        self.assertEqual(client.stored, [])
        self.assertEqual(client.expunged, 0)

    def test_dry_run_neither_ingests_nor_deletes(self):
        resolve, ingest, calls = accept_only(f"inbox-abc@{DOMAIN}")
        engine = ImapEngine(
            host="h",
            port=993,
            username="u",
            password="p",
            dry_run=True,
            resolve=resolve,
            ingest=ingest,
        )
        client = FakeClient({b"1": build_raw()})
        engine.poll_once(client)
        self.assertEqual(calls, [])  # ingest never called
        self.assertEqual(client.stored, [])  # mailbox untouched
        self.assertEqual(client.expunged, 0)


@override_settings(USER_EMAIL_INBOX_DOMAIN=DOMAIN)
class BuildEngineTests(SimpleTestCase):
    def test_builds_imaps_engine_from_dsn(self):
        dsn = parse_dsn("imaps://user:pass@mail.example.com:993/Archive?poll=45")
        engine = build_engine(dsn)
        self.assertIsInstance(engine, ImapEngine)
        self.assertEqual(engine.host, "mail.example.com")
        self.assertEqual(engine.port, 993)
        # USER_EMAIL_INBOX_DOMAIN is appended to the login name by default.
        self.assertEqual(engine.username, f"user@{DOMAIN}")
        self.assertEqual(engine.password, "pass")
        self.assertEqual(engine.mailbox, "Archive")
        self.assertEqual(engine.poll_interval, 45)
        self.assertTrue(engine.use_ssl)

    def test_domain_in_username_can_be_disabled(self):
        dsn = parse_dsn("imaps://user:pass@mail.example.com?domain_in_username=0")
        self.assertEqual(build_engine(dsn).username, "user")

    def test_domain_in_username_can_be_overridden(self):
        dsn = parse_dsn(
            "imaps://user:pass@mail.example.com?domain_in_username=@infomaniak.com"
        )
        self.assertEqual(build_engine(dsn).username, "user@infomaniak.com")

    def test_dry_run_flag_from_dsn(self):
        self.assertFalse(build_engine(parse_dsn("imaps://u:p@m.test")).dry_run)
        self.assertTrue(build_engine(parse_dsn("imaps://u:p@m.test?dry_run=1")).dry_run)

    def test_host_port_override(self):
        dsn = parse_dsn("imaps://user:pass@mail.example.com")
        engine = build_engine(dsn, host="other.test", port=1993)
        self.assertEqual(engine.host, "other.test")
        self.assertEqual(engine.port, 1993)

    def test_plain_imap_engine_is_not_ssl(self):
        dsn = parse_dsn("imap://user:pass@mail.example.com")
        engine = build_engine(dsn)
        self.assertFalse(engine.use_ssl)

    def test_unknown_scheme_still_raises(self):
        dsn = parse_dsn("smtp://localhost")
        object.__setattr__(dsn, "scheme", "pop3")
        with self.assertRaises(CommandError):
            build_engine(dsn)


@override_settings(USER_EMAIL_INBOX_DOMAIN=DOMAIN)
class PollThroughRealPipelineTests(TestCase):
    """End-to-end: the engine drives the real resolve/ingest, enforcing the
    inbox policy and deleting every message it handles."""

    def setUp(self):
        self.user = User.objects.create_user(username="u", password="p")
        self.user.user_permissions.add(
            Permission.objects.get(
                codename="use_email_inbox",
                content_type__app_label="task_processor",
            )
        )
        self.inbox = EmailInbox.objects.create(user=self.user, identifier="inbox-abc")
        AllowedSender.objects.create(inbox=self.inbox, email="sender@example.com")
        self.engine = ImapEngine(host="h", port=993, username="u", password="p")

    def _poll(self, raw):
        client = FakeClient({b"1": raw})
        self.engine.poll_once(client)
        return client

    def test_trusted_sender_creates_task_and_deletes(self):
        client = self._poll(build_raw(sender="sender@example.com"))
        self.assertEqual(Item.objects.filter(user=self.user).count(), 1)
        self.assertEqual(client.stored, [(b"1", "+FLAGS", "\\Deleted")])
        self.assertEqual(client.expunged, 1)

    def test_untrusted_sender_dropped_and_deleted(self):
        client = self._poll(build_raw(sender="stranger@evil.test"))
        self.assertEqual(Item.objects.filter(user=self.user).count(), 0)
        self.assertEqual(client.stored, [(b"1", "+FLAGS", "\\Deleted")])
        self.assertEqual(client.expunged, 1)

    def test_disabled_inbox_dropped_and_deleted(self):
        self.inbox.enabled = False
        self.inbox.save(update_fields=["enabled"])
        client = self._poll(build_raw(sender="sender@example.com"))
        self.assertEqual(Item.objects.filter(user=self.user).count(), 0)
        self.assertEqual(client.stored, [(b"1", "+FLAGS", "\\Deleted")])
        self.assertEqual(client.expunged, 1)

    def test_dry_run_creates_no_task_and_keeps_mail(self):
        self.engine.dry_run = True
        client = self._poll(build_raw(sender="sender@example.com"))
        self.assertEqual(Item.objects.filter(user=self.user).count(), 0)
        self.assertEqual(client.stored, [])
        self.assertEqual(client.expunged, 0)
