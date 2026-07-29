import hashlib
import os
import uuid

from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone


def document_upload_path(instance, filename):
    _, ext = os.path.splitext(filename)
    new_filename = f"{uuid.uuid4().hex}{ext}"
    date_prefix = timezone.now().strftime("%Y/%m/%d")
    return f"documents/{date_prefix}/{new_filename}"


def compute_content_hash(file) -> str:
    """SHA-256 hex digest of a Django File, streamed; rewinds the file."""
    hasher = hashlib.sha256()
    file.seek(0)
    for chunk in file.chunks():
        hasher.update(chunk)
    file.seek(0)
    return hasher.hexdigest()


class Document(models.Model):
    FILE_NAME_MAX_LENGTH = 255

    item = models.ForeignKey(
        "task_processor.Item",
        on_delete=models.CASCADE,
        related_name="documents",
    )
    file = models.FileField(upload_to=document_upload_path, max_length=500)
    file_name = models.CharField(max_length=FILE_NAME_MAX_LENGTH)
    file_size = models.BigIntegerField()
    content_type = models.CharField(max_length=100, blank=True, default="")
    # SHA-256 of the file content, filled automatically on save; used to
    # refuse duplicate attachments on the same item regardless of file name.
    content_hash = models.CharField(
        max_length=64, blank=True, default="", db_index=True
    )
    uploaded_at = models.DateTimeField(default=timezone.now)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="documents",
    )

    class Meta:
        ordering = ["-uploaded_at"]
        indexes = [
            models.Index(fields=["item"]),
            models.Index(fields=["user"]),
            models.Index(fields=["uploaded_at"]),
        ]
        constraints = [
            # DB-level backing for the duplicate check in uploads.attach_document:
            # the exists()-then-create there is racy under concurrent uploads.
            # Empty hashes (backfill couldn't read the file) are exempt.
            models.UniqueConstraint(
                fields=["item", "content_hash"],
                condition=~models.Q(content_hash=""),
                name="unique_document_content_per_item",
            ),
        ]

    def __str__(self):
        return self.file_name

    def save(self, *args, **kwargs):
        # Hash here (not in the views) so every creation path — web upload,
        # mail inbox attachments, shell — gets a content hash.
        if not self.content_hash and self.file:
            self.content_hash = compute_content_hash(self.file)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.file:
            storage = self.file.storage
            if storage.exists(self.file.name):
                storage.delete(self.file.name)
        super().delete(*args, **kwargs)

    @property
    def is_audio(self):
        """Whether the stored content is playable audio (in-browser preview)."""
        return self.content_type.startswith("audio/")

    @property
    def icon(self):
        """Sprite name for the stored content type (image / audio / generic)."""
        if self.content_type.startswith("image/"):
            return "lucide-image"
        if self.is_audio:
            return "lucide-music"
        return "lucide-file"

    @property
    def file_size_display(self):
        size = self.file_size
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / (1024 * 1024):.1f} MB"


@receiver(post_delete, sender=Document)
def delete_document_file(sender, instance, **kwargs):
    if instance.file:
        storage = instance.file.storage
        if storage.exists(instance.file.name):
            storage.delete(instance.file.name)
