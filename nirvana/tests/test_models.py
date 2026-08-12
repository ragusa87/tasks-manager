from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from nirvana.importer import (
    PHASE_CREATING,
    PHASE_PARENTS,
    PHASE_TAGS,
    PHASE_WIPING,
)
from nirvana.models import ImportJob, heartbeat_max_age


class TestPhaseChecklist(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="phases", password="x")

    def _job(self, **kwargs):
        return ImportJob.objects.create(user=self.user, file_path="x.json", **kwargs)

    def test_pending_job_all_todo(self):
        job = self._job()
        self.assertEqual(
            job.phase_checklist,
            [
                {"label": PHASE_CREATING, "state": "todo", "count": ""},
                {"label": PHASE_PARENTS, "state": "todo", "count": ""},
                {"label": PHASE_TAGS, "state": "todo", "count": ""},
            ],
        )

    def test_wipe_adds_leading_phase(self):
        job = self._job(wipe_existing=True, phase=PHASE_WIPING)
        self.assertEqual(
            job.phase_checklist,
            [
                {"label": PHASE_WIPING, "state": "current", "count": ""},
                {"label": PHASE_CREATING, "state": "todo", "count": ""},
                {"label": PHASE_PARENTS, "state": "todo", "count": ""},
                {"label": PHASE_TAGS, "state": "todo", "count": ""},
            ],
        )

    def test_running_marks_earlier_phases_done(self):
        job = self._job(status=ImportJob.Status.RUNNING, phase=PHASE_PARENTS)
        self.assertEqual(
            job.phase_checklist,
            [
                {"label": PHASE_CREATING, "state": "done", "count": ""},
                {"label": PHASE_PARENTS, "state": "current", "count": ""},
                {"label": PHASE_TAGS, "state": "todo", "count": ""},
            ],
        )

    def test_current_phase_shows_item_counter(self):
        job = self._job(
            status=ImportJob.Status.RUNNING,
            phase=PHASE_CREATING,
            progress_current=2,
            progress_total=232,
        )
        self.assertEqual(
            job.phase_checklist,
            [
                {"label": PHASE_CREATING, "state": "current", "count": "2/232"},
                {"label": PHASE_PARENTS, "state": "todo", "count": ""},
                {"label": PHASE_TAGS, "state": "todo", "count": ""},
            ],
        )

    def test_success_marks_everything_done(self):
        job = self._job(status=ImportJob.Status.SUCCESS, phase=PHASE_TAGS)
        self.assertEqual(
            [phase["state"] for phase in job.phase_checklist],
            ["done", "done", "done"],
        )


class TestIsStale(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="staleness", password="x")

    def _job(self, heartbeat_age=None, **kwargs):
        job = ImportJob.objects.create(user=self.user, file_path="x.json", **kwargs)
        if heartbeat_age is not None:
            job.heartbeat = timezone.now() - heartbeat_age
        return job

    def test_fresh_running_job_is_not_stale(self):
        job = self._job(
            status=ImportJob.Status.RUNNING, heartbeat_age=timedelta(seconds=30)
        )
        self.assertFalse(job.is_stale)

    def test_silent_running_job_is_stale(self):
        job = self._job(
            status=ImportJob.Status.RUNNING,
            heartbeat_age=heartbeat_max_age() + timedelta(minutes=1),
        )
        self.assertTrue(job.is_stale)

    def test_pending_job_falls_back_to_created_at(self):
        job = self._job(status=ImportJob.Status.PENDING)
        self.assertFalse(job.is_stale)
        ImportJob.objects.filter(pk=job.pk).update(
            created_at=timezone.now() - heartbeat_max_age() - timedelta(minutes=1)
        )
        job.refresh_from_db()
        self.assertTrue(job.is_stale)

    def test_finished_job_is_never_stale(self):
        job = self._job(
            status=ImportJob.Status.SUCCESS,
            heartbeat_age=heartbeat_max_age() + timedelta(hours=2),
        )
        self.assertFalse(job.is_stale)
