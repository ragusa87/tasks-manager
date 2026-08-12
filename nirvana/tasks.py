"""Celery tasks running and supervising Nirvana JSON imports."""

import json
import logging

from celery import shared_task
from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from django.db.models import F
from django.utils import timezone

from .cancellation import clear_cancellation, is_cancellation_requested
from .importer import PHASE_WIPING, NirvanaImporter
from .models import ImportJob

logger = logging.getLogger(__name__)

# Write progress to the DB at most every N items (plus on phase change and last item).
PROGRESS_WRITE_EVERY = 25


class ImportCancelled(Exception):
    """Raised inside the import loop when the user requested cancellation."""


def friendly_error(exc):
    """User-facing failure text; the raw exception stays in the logs only."""
    if isinstance(exc, json.JSONDecodeError):
        return "The uploaded file is not valid JSON."
    if isinstance(exc, OSError):
        return "The uploaded file could not be read."
    return "The import failed unexpectedly. Please try again."


@shared_task(bind=True, name="nirvana.tasks.run_nirvana_import")
def run_nirvana_import(
    self, file_path: str, user_id: int, wipe_existing: bool, import_job_id: int
):
    """Import a Nirvana export previously uploaded to ``default_storage``.

    Progress is persisted on the ImportJob row so the UX can poll it. The
    import deliberately runs without an outer transaction: progress updates
    would otherwise stay invisible to the web process until commit, and the
    import is idempotent (update_or_create keyed on nirvana_id).

    Every DB write also refreshes the job's heartbeat, so
    cleanup_stale_import_jobs can tell a live import from a dead one.
    The uploaded file is deleted whether the import succeeds or fails.
    All status transitions are compare-and-set (filtered updates), so the
    task, the cleanup task and the cancel view can never overwrite each
    other's final state.
    """
    claimed = ImportJob.objects.filter(
        pk=import_job_id, status=ImportJob.Status.PENDING
    ).update(
        status=ImportJob.Status.RUNNING,
        celery_task_id=self.request.id or "",
        heartbeat=timezone.now(),
    )
    if not claimed:
        # The job was cancelled or reaped as stale while still queued.
        # Whoever ended it also removed the upload — touching the file here
        # could sabotage a concurrent run of the same job id.
        logger.warning(
            "Nirvana import job %s is no longer pending; skipping", import_job_id
        )
        return {"skipped": True}

    job = ImportJob.objects.get(pk=import_job_id)

    try:

        def check_cancelled():
            if is_cancellation_requested(job.pk):
                raise ImportCancelled()

        check_cancelled()
        user = User.objects.get(pk=user_id)

        with default_storage.open(file_path) as f:
            nirvana_items = json.load(f)

        last_phase = [None]

        def progress(phase, current, total):
            if (
                phase != last_phase[0]
                or current % PROGRESS_WRITE_EVERY == 0
                or current == total
            ):
                check_cancelled()
                last_phase[0] = phase
                ImportJob.objects.filter(pk=job.pk).update(
                    phase=phase,
                    progress_current=current,
                    progress_total=total,
                    heartbeat=timezone.now(),
                )

        importer = NirvanaImporter(log=logger.info, progress=progress)

        if wipe_existing:
            check_cancelled()
            ImportJob.objects.filter(pk=job.pk).update(
                phase=PHASE_WIPING, heartbeat=timezone.now()
            )
            importer.delete_existing_data(user)

        result = importer.import_items(nirvana_items, user)

        ImportJob.objects.filter(pk=job.pk, status=ImportJob.Status.RUNNING).update(
            status=ImportJob.Status.SUCCESS,
            created_count=result.created,
            updated_count=result.updated,
            progress_current=F("progress_total"),
            heartbeat=timezone.now(),
        )
        return {"created": result.created, "updated": result.updated}
    except ImportCancelled:
        logger.info("Nirvana import job %s cancelled by user", job.pk)
        ImportJob.objects.filter(pk=job.pk, status=ImportJob.Status.RUNNING).update(
            status=ImportJob.Status.CANCELLED,
            heartbeat=timezone.now(),
        )
        return {"cancelled": True}
    except Exception as exc:
        logger.exception("Nirvana import job %s failed", job.pk)
        ImportJob.objects.filter(pk=job.pk, status=ImportJob.Status.RUNNING).update(
            status=ImportJob.Status.FAILURE,
            error_message=friendly_error(exc),
            heartbeat=timezone.now(),
        )
        raise
    finally:
        clear_cancellation(job.pk)
        job.delete_upload()


@shared_task(bind=True, name="nirvana.tasks.cleanup_stale_import_jobs")
def cleanup_stale_import_jobs(self):
    """Fail pending/running jobs whose worker went silent and delete their upload.

    Runs periodically via Celery beat. Without it, a crashed worker would
    leave a job "running" forever, blocking the upload form and leaking the
    uploaded file.
    """
    cleared = []
    for job in ImportJob.stale():
        # Compare-and-set on status AND heartbeat: a worker that finished or
        # heartbeated after the stale query must not get its state clobbered.
        reaped = ImportJob.objects.filter(
            pk=job.pk,
            status__in=ImportJob.UNFINISHED_STATUSES,
            heartbeat=job.heartbeat,
        ).update(
            status=ImportJob.Status.FAILURE,
            error_message=(
                "Import stalled: no sign of life from the worker since "
                f"{job.last_seen:%Y-%m-%d %H:%M} UTC."
            ),
        )
        if not reaped:
            continue
        logger.warning(
            "Cleared stale Nirvana import job %s (last seen %s)",
            job.pk,
            job.last_seen,
        )
        job.delete_upload()
        cleared.append(job.pk)
    return cleared
