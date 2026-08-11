import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from django.db import models
from django.db.models.functions import Coalesce
from django.utils import timezone

logger = logging.getLogger(__name__)


def heartbeat_max_age():
    """How long a pending/running job may go without a sign of life before it
    is considered dead (worker crashed or was killed) and gets cleaned up by
    nirvana.tasks.cleanup_stale_import_jobs or the cancel button."""
    return timedelta(seconds=settings.NIRVANA_IMPORT_HEARTBEAT_MAX_AGE)


class ImportJob(models.Model):
    """Tracks a Nirvana JSON import running in Celery, for UX progress display."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILURE = "failure", "Failure"
        CANCELLED = "cancelled", "Cancelled"

    UNFINISHED_STATUSES = (Status.PENDING, Status.RUNNING)

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="nirvana_import_jobs"
    )
    file_path = models.CharField(
        max_length=500, help_text="default_storage-relative path of the upload"
    )
    wipe_existing = models.BooleanField(default=False)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    phase = models.CharField(max_length=100, blank=True)
    progress_current = models.PositiveIntegerField(default=0)
    progress_total = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    celery_task_id = models.CharField(max_length=64, blank=True)
    heartbeat = models.DateTimeField(
        null=True, blank=True, help_text="Last sign of life from the worker"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Nirvana import #{self.pk} for {self.user} ({self.status})"

    @classmethod
    def stale(cls):
        """Unfinished jobs whose worker went silent (see heartbeat_max_age).

        Pending jobs have no heartbeat yet, so their creation time counts
        as the last sign of life.
        """
        cutoff = timezone.now() - heartbeat_max_age()
        return (
            cls.objects.filter(status__in=cls.UNFINISHED_STATUSES)
            .annotate(last_activity=Coalesce("heartbeat", "created_at"))
            .filter(last_activity__lt=cutoff)
        )

    def delete_upload(self):
        """Delete the uploaded file; never raises (cleanup best effort)."""
        try:
            default_storage.delete(self.file_path)
        except Exception:
            logger.exception(
                "Could not delete uploaded Nirvana file %s", self.file_path
            )

    @property
    def last_seen(self):
        """Last sign of life: heartbeat, or creation time before the worker starts."""
        return self.heartbeat or self.created_at

    @property
    def is_stale(self):
        return (
            not self.is_finished
            and self.last_seen < timezone.now() - heartbeat_max_age()
        )

    @property
    def is_finished(self):
        return self.status in (
            self.Status.SUCCESS,
            self.Status.FAILURE,
            self.Status.CANCELLED,
        )

    @property
    def percent(self):
        if not self.progress_total:
            return 0
        return int(self.progress_current * 100 / self.progress_total)

    @property
    def phase_checklist(self):
        """The job's phases in order, each with a done/current/todo state.

        Drives the checklist shown while the import is polled; a finished
        job renders its summary line instead.
        """
        from .importer import IMPORT_PHASES, PHASE_WIPING

        phases = ([PHASE_WIPING] if self.wipe_existing else []) + IMPORT_PHASES
        current_index = phases.index(self.phase) if self.phase in phases else -1
        checklist = []
        for index, label in enumerate(phases):
            if self.status == self.Status.SUCCESS or index < current_index:
                state = "done"
            elif index == current_index:
                state = "current"
            else:
                state = "todo"
            # Item counter for the pass being executed; the wiping phase is a
            # single bulk operation and has no per-item progress.
            count = ""
            if state == "current" and self.progress_total and label != PHASE_WIPING:
                count = f"{self.progress_current}/{self.progress_total}"
            checklist.append({"label": label, "state": state, "count": count})
        return checklist
