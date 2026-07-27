import secrets
import string

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower

# Gate for the whole email-to-task feature. Checked with user.has_perm() in
# views and in the mail ingestion pipeline. The carrier group (created by a
# data migration) holds this permission so users can be enrolled via the admin.
EMAIL_INBOX_PERMISSION = "task_processor.use_email_inbox"
EMAIL_INBOX_GROUP = "Email inbox"

IDENTIFIER_ALPHABET = string.ascii_lowercase + string.digits


def generate_inbox_identifier():
    return "inbox-" + "".join(secrets.choice(IDENTIFIER_ALPHABET) for _ in range(8))


class EmailInbox(models.Model):
    """Per-user configuration for receiving tasks by email.

    The identifier is a random capability token used as the local part of the
    user's inbox address; it can be regenerated if it leaks.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_inbox",
    )
    identifier = models.CharField(
        max_length=64, unique=True, default=generate_inbox_identifier
    )
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "email inboxes"
        permissions = [("use_email_inbox", "Can use the email inbox")]

    def __str__(self):
        return self.address

    @property
    def address(self):
        return f"{self.identifier}@{settings.USER_EMAIL_INBOX_DOMAIN}"

    def regenerate_identifier(self):
        while True:
            candidate = generate_inbox_identifier()
            if not EmailInbox.objects.filter(identifier=candidate).exists():
                break
        self.identifier = candidate
        self.save(update_fields=["identifier", "updated_at"])

    def is_sender_allowed(self, email):
        return self.allowed_senders.filter(email=email.strip().lower()).exists()

    @classmethod
    def resolve(cls, local_part):
        return cls.objects.select_related("user").filter(identifier=local_part).first()


class AllowedSender(models.Model):
    """Whitelisted FROM address for an email inbox."""

    inbox = models.ForeignKey(
        EmailInbox, on_delete=models.CASCADE, related_name="allowed_senders"
    )
    email = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["email"]
        constraints = [
            models.UniqueConstraint(
                Lower("email"), "inbox", name="uniq_sender_per_inbox"
            )
        ]

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)
