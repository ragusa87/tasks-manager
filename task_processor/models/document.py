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


class Document(models.Model):
    item = models.ForeignKey(
        "task_processor.Item",
        on_delete=models.CASCADE,
        related_name="documents",
    )
    file = models.FileField(upload_to=document_upload_path, max_length=500)
    file_name = models.CharField(max_length=255)
    file_size = models.BigIntegerField()
    content_type = models.CharField(max_length=100, blank=True, default="")
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

    def __str__(self):
        return self.file_name

    def delete(self, *args, **kwargs):
        if self.file:
            storage = self.file.storage
            if storage.exists(self.file.name):
                storage.delete(self.file.name)
        super().delete(*args, **kwargs)

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
