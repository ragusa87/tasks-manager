from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse

from task_processor.models import AllowedSender, EmailInbox


def grant_permission(user):
    user.user_permissions.add(
        Permission.objects.get(
            codename="use_email_inbox",
            content_type__app_label="task_processor",
        )
    )


class EmailInboxViewsTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="member", email="member@example.com", password="testpass"
        )
        grant_permission(self.user)
        self.outsider = User.objects.create_user(
            username="outsider", email="outsider@example.com", password="testpass"
        )


class SettingsPageTests(EmailInboxViewsTestCase):
    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("email_inbox_settings"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_user_without_permission_gets_403(self):
        self.client.force_login(self.outsider)
        response = self.client.get(reverse("email_inbox_settings"))
        self.assertEqual(response.status_code, 403)

    def test_member_sees_settings_and_inbox_is_provisioned(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("email_inbox_settings"))
        self.assertEqual(response.status_code, 200)
        inbox = EmailInbox.objects.get(user=self.user)
        self.assertContains(response, inbox.address)

    def test_nav_link_visibility(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, reverse("email_inbox_settings"))

        self.client.force_login(self.outsider)
        response = self.client.get(reverse("dashboard"))
        self.assertNotContains(response, reverse("email_inbox_settings"))

    def test_disable_inbox(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("email_inbox_settings"), {})
        self.assertEqual(response.status_code, 302)
        inbox = EmailInbox.objects.get(user=self.user)
        self.assertFalse(inbox.enabled)


class RegenerateTests(EmailInboxViewsTestCase):
    def test_regenerate_changes_identifier(self):
        self.client.force_login(self.user)
        inbox = EmailInbox.objects.create(user=self.user)
        old_identifier = inbox.identifier
        response = self.client.post(reverse("email_inbox_regenerate"))
        self.assertEqual(response.status_code, 302)
        inbox.refresh_from_db()
        self.assertNotEqual(inbox.identifier, old_identifier)
        self.assertTrue(inbox.identifier.startswith("inbox-"))

    def test_regenerate_requires_permission(self):
        self.client.force_login(self.outsider)
        response = self.client.post(reverse("email_inbox_regenerate"))
        self.assertEqual(response.status_code, 403)


class AllowedSenderTests(EmailInboxViewsTestCase):
    def test_add_sender(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("email_inbox_sender_add"), {"email": "Boss@Example.COM"}
        )
        self.assertEqual(response.status_code, 302)
        sender = AllowedSender.objects.get(inbox__user=self.user)
        self.assertEqual(sender.email, "boss@example.com")

    def test_duplicate_sender_rejected(self):
        self.client.force_login(self.user)
        inbox = EmailInbox.objects.create(user=self.user)
        AllowedSender.objects.create(inbox=inbox, email="boss@example.com")
        response = self.client.post(
            reverse("email_inbox_sender_add"), {"email": "boss@example.com"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already whitelisted")
        self.assertEqual(AllowedSender.objects.count(), 1)

    def test_delete_sender(self):
        self.client.force_login(self.user)
        inbox = EmailInbox.objects.create(user=self.user)
        sender = AllowedSender.objects.create(inbox=inbox, email="boss@example.com")
        response = self.client.post(
            reverse("email_inbox_sender_delete", args=[sender.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(AllowedSender.objects.count(), 0)

    def test_add_sender_rejects_get(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("email_inbox_sender_add"))
        self.assertEqual(response.status_code, 405)

    def test_delete_sender_rejects_get(self):
        self.client.force_login(self.user)
        inbox = EmailInbox.objects.create(user=self.user)
        sender = AllowedSender.objects.create(inbox=inbox, email="boss@example.com")
        response = self.client.get(
            reverse("email_inbox_sender_delete", args=[sender.pk])
        )
        self.assertEqual(response.status_code, 405)
        self.assertEqual(AllowedSender.objects.count(), 1)

    def test_cannot_delete_other_users_sender(self):
        grant_permission(self.outsider)
        other_inbox = EmailInbox.objects.create(user=self.outsider)
        sender = AllowedSender.objects.create(
            inbox=other_inbox, email="boss@example.com"
        )
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("email_inbox_sender_delete", args=[sender.pk])
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(AllowedSender.objects.count(), 1)
