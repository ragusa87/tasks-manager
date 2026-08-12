import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings
from django.utils import timezone

from nirvana.cancellation import is_cancellation_requested, request_cancellation
from nirvana.models import ImportJob, heartbeat_max_age
from nirvana.tasks import cleanup_stale_import_jobs, run_nirvana_import
from task_processor.models import Item

from .test_importer import nirvana_item

STORAGES_OVERRIDE = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# Test settings use DummyCache; cancellation flags need a real (local) cache.
CACHES_OVERRIDE = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


@override_settings(STORAGES=STORAGES_OVERRIDE)
class TestRunNirvanaImport(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="celery", password="x")

    def _make_job(self, items, wipe=False):
        path = default_storage.save(
            f"nirvana_imports/{self.user.id}/test.json",
            ContentFile(json.dumps(items).encode()),
        )
        job = ImportJob.objects.create(
            user=self.user, file_path=path, wipe_existing=wipe
        )
        return job, path

    def test_success_updates_job_and_deletes_file(self):
        job, path = self._make_job([nirvana_item(id="t-1")])
        run_nirvana_import(path, self.user.id, False, job.id)

        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.SUCCESS)
        self.assertEqual(job.created_count, 1)
        self.assertEqual(job.updated_count, 0)
        self.assertEqual(job.progress_current, job.progress_total)
        self.assertEqual(job.percent, 100)
        self.assertFalse(default_storage.exists(path))
        self.assertTrue(Item.objects.filter(nirvana_id="t-1").exists())

    def test_failure_marks_job_and_still_deletes_file(self):
        path = default_storage.save(
            f"nirvana_imports/{self.user.id}/bad.json", ContentFile(b"not json")
        )
        job = ImportJob.objects.create(user=self.user, file_path=path)

        with self.assertRaises(json.JSONDecodeError):
            run_nirvana_import(path, self.user.id, False, job.id)

        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.FAILURE)
        # A sanitized message, not the raw exception text.
        self.assertEqual(job.error_message, "The uploaded file is not valid JSON.")
        self.assertFalse(default_storage.exists(path))

    def test_non_pending_job_is_skipped(self):
        # A job cancelled or reaped while still queued must not be resurrected,
        # and its file (owned by whoever ended the job) must not be touched.
        job, path = self._make_job([nirvana_item(id="t-1")])
        ImportJob.objects.filter(pk=job.pk).update(status=ImportJob.Status.CANCELLED)

        result = run_nirvana_import(path, self.user.id, False, job.id)

        self.assertEqual(result, {"skipped": True})
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.CANCELLED)
        self.assertFalse(Item.objects.exists())
        self.assertTrue(default_storage.exists(path))

    def test_wipe_existing_deletes_previous_items(self):
        old = Item.objects.create(title="Old", user=self.user)
        job, path = self._make_job([nirvana_item(id="t-1")], wipe=True)
        run_nirvana_import(path, self.user.id, True, job.id)

        self.assertFalse(Item.objects.filter(pk=old.pk).exists())
        self.assertTrue(Item.objects.filter(nirvana_id="t-1").exists())

    def test_heartbeat_is_updated(self):
        job, path = self._make_job([nirvana_item(id="t-1")])
        self.assertIsNone(job.heartbeat)
        before = timezone.now()
        run_nirvana_import(path, self.user.id, False, job.id)

        job.refresh_from_db()
        self.assertIsNotNone(job.heartbeat)
        self.assertGreaterEqual(job.heartbeat, before)

    def test_progress_is_recorded(self):
        items = [nirvana_item(id=f"t-{i}") for i in range(3)]
        job, path = self._make_job(items)
        run_nirvana_import(path, self.user.id, False, job.id)

        job.refresh_from_db()
        self.assertEqual(job.progress_total, 3)
        self.assertEqual(job.progress_current, 3)
        # Last phase written is the final pass
        self.assertEqual(job.phase, "Assigning tags")


@override_settings(STORAGES=STORAGES_OVERRIDE, CACHES=CACHES_OVERRIDE)
class TestCancelImport(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="canceller", password="x")

    def _make_job(self, items):
        path = default_storage.save(
            f"nirvana_imports/{self.user.id}/cancel.json",
            ContentFile(json.dumps(items).encode()),
        )
        return ImportJob.objects.create(user=self.user, file_path=path), path

    def test_cancelled_job_stops_and_cleans_up(self):
        job, path = self._make_job([nirvana_item(id="t-1")])
        request_cancellation(job.pk)
        run_nirvana_import(path, self.user.id, False, job.id)

        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.CANCELLED)
        self.assertFalse(Item.objects.exists())
        self.assertFalse(default_storage.exists(path))
        # Flag is cleared so a later job with a recycled id is unaffected.
        self.assertFalse(is_cancellation_requested(job.pk))

    def test_uncancelled_job_completes(self):
        job, path = self._make_job([nirvana_item(id="t-1")])
        run_nirvana_import(path, self.user.id, False, job.id)

        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.SUCCESS)


@override_settings(STORAGES=STORAGES_OVERRIDE)
class TestCleanupStaleImportJobs(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="janitor", password="x")

    def _job(self, heartbeat_age=None, **kwargs):
        path = default_storage.save(
            f"nirvana_imports/{self.user.id}/stale.json", ContentFile(b"[]")
        )
        job = ImportJob.objects.create(user=self.user, file_path=path, **kwargs)
        if heartbeat_age is not None:
            ImportJob.objects.filter(pk=job.pk).update(
                heartbeat=timezone.now() - heartbeat_age
            )
            job.refresh_from_db()
        return job

    def test_stale_running_job_is_failed_and_file_deleted(self):
        job = self._job(
            status=ImportJob.Status.RUNNING,
            heartbeat_age=heartbeat_max_age() + timedelta(minutes=1),
        )
        cleared = cleanup_stale_import_jobs()

        job.refresh_from_db()
        self.assertEqual(cleared, [job.pk])
        self.assertEqual(job.status, ImportJob.Status.FAILURE)
        self.assertIn("stalled", job.error_message)
        self.assertFalse(default_storage.exists(job.file_path))

    def test_fresh_running_job_is_kept(self):
        job = self._job(
            status=ImportJob.Status.RUNNING, heartbeat_age=timedelta(seconds=30)
        )
        self.assertEqual(cleanup_stale_import_jobs(), [])

        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.RUNNING)
        self.assertTrue(default_storage.exists(job.file_path))

    def test_stale_pending_job_uses_created_at(self):
        # A pending job never got a heartbeat: created_at is the last sign of life.
        job = self._job(status=ImportJob.Status.PENDING)
        ImportJob.objects.filter(pk=job.pk).update(
            created_at=timezone.now() - heartbeat_max_age() - timedelta(minutes=1)
        )
        cleared = cleanup_stale_import_jobs()

        job.refresh_from_db()
        self.assertEqual(cleared, [job.pk])
        self.assertEqual(job.status, ImportJob.Status.FAILURE)
        self.assertFalse(default_storage.exists(job.file_path))

    def test_finished_jobs_are_untouched(self):
        job = self._job(
            status=ImportJob.Status.SUCCESS,
            heartbeat_age=heartbeat_max_age() + timedelta(hours=5),
        )
        self.assertEqual(cleanup_stale_import_jobs(), [])

        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.SUCCESS)
