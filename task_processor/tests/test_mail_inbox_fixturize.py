from io import StringIO

from django.core import management
from django.test import TestCase

from task_processor.models import AllowedSender, EmailInbox
from task_processor.models.email_inbox import (
    EMAIL_INBOX_GROUP,
    EMAIL_INBOX_PERMISSION,
)


class FixturizeEmailInboxTests(TestCase):
    def run_command(self):
        out = StringIO()
        management.call_command("fixturize", "--items-per-user=4", stdout=out)
        return out.getvalue()

    def test_first_user_gets_email_inbox(self):
        output = self.run_command()

        inbox = EmailInbox.objects.get(user__username="user1")
        self.assertEqual(inbox.identifier, "inbox-user1")
        self.assertTrue(inbox.enabled)
        self.assertTrue(inbox.user.has_perm(EMAIL_INBOX_PERMISSION))
        self.assertTrue(inbox.user.groups.filter(name=EMAIL_INBOX_GROUP).exists())
        self.assertTrue(
            AllowedSender.objects.filter(
                inbox=inbox, email="user1@example.com"
            ).exists()
        )
        self.assertIn(inbox.address, output)

    def test_other_users_get_no_inbox(self):
        self.run_command()
        self.assertFalse(EmailInbox.objects.filter(user__username="user2").exists())

    def test_rerun_is_idempotent(self):
        self.run_command()
        self.run_command()
        self.assertEqual(EmailInbox.objects.count(), 1)
        self.assertEqual(AllowedSender.objects.count(), 1)
