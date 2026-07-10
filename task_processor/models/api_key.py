import hashlib
import secrets

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class ApiKey(models.Model):
    """API key for stateless REST authentication.

    The raw key is shown once at creation; only its SHA-256 hash is stored.
    Unsalted SHA-256 is appropriate here because keys are high-entropy random
    tokens (not human passwords) and the unique index allows O(1) lookup.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="api_keys")
    name = models.CharField(
        max_length=100, help_text="Label to identify this key, e.g. 'iOS shortcut'"
    )
    prefix = models.CharField(max_length=8, editable=False)
    hashed_key = models.CharField(max_length=64, unique=True, editable=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "API key"

    def __str__(self):
        return f"{self.name} ({self.prefix}...)"

    @staticmethod
    def hash_key(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode()).hexdigest()

    def assign_new_key(self) -> str:
        """Set prefix and hashed_key on the instance, return the raw key."""
        raw_key = secrets.token_urlsafe(32)
        self.prefix = raw_key[:8]
        self.hashed_key = self.hash_key(raw_key)
        return raw_key

    @classmethod
    def generate(cls, user, name: str) -> tuple["ApiKey", str]:
        """Create and save a new key for user, returning (instance, raw_key)."""
        instance = cls(user=user, name=name)
        raw_key = instance.assign_new_key()
        instance.save()
        return instance, raw_key

    @classmethod
    def authenticate(cls, raw_key: str) -> "ApiKey | None":
        """Return the active ApiKey matching raw_key, or None.

        last_used_at is only refreshed once it is older than
        settings.API_KEY_LAST_USED_UPDATE_INTERVAL, to avoid one DB write
        per authenticated request.
        """
        api_key = (
            cls.objects.select_related("user")
            .filter(
                hashed_key=cls.hash_key(raw_key),
                is_active=True,
                user__is_active=True,
            )
            .first()
        )
        if api_key and (
            api_key.last_used_at is None
            or timezone.now() - api_key.last_used_at
            > settings.API_KEY_LAST_USED_UPDATE_INTERVAL
        ):
            cls.objects.filter(pk=api_key.pk).update(last_used_at=timezone.now())
        return api_key
