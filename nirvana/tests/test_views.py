import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from nirvana.cancellation import is_cancellation_requested
from nirvana.models import ImportJob

CACHES_OVERRIDE = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}

STORAGES_OVERRIDE = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(STORAGES=STORAGES_OVERRIDE)
class TestNirvanaImportView(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="web", password="pass")
        self.client = Client()
        self.client.login(username="web", password="pass")
        self.url = reverse("nirvana_import")

    def test_login_required(self):
        response = Client().get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])

    def test_get_renders_form(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Start import")

    @override_settings(ALLOW_FILES_UPLOAD=False)
    def test_page_still_renders_when_uploads_disabled(self):
        # The page stays reachable; only the upload itself is refused.
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    @override_settings(ALLOW_FILES_UPLOAD=False)
    @patch("nirvana.views.run_nirvana_import")
    def test_upload_rejected_by_form_when_uploads_disabled(self, mock_task):
        export = SimpleUploadedFile("export.json", json.dumps([{"id": "1"}]).encode())
        response = self.client.post(self.url, {"file": export, "wipe_existing": "on"})
        self.assertEqual(response.status_code, 200)  # re-rendered with the error
        self.assertFormError(
            response.context["form"],
            "file",
            "File uploads are disabled on this instance.",
        )
        self.assertFalse(ImportJob.objects.exists())
        mock_task.delay.assert_not_called()

    @patch("nirvana.views.run_nirvana_import")
    def test_post_creates_job_and_dispatches_task(self, mock_task):
        export = SimpleUploadedFile("export.json", json.dumps([{"id": "1"}]).encode())
        response = self.client.post(self.url, {"file": export, "wipe_existing": "on"})

        self.assertRedirects(response, self.url)
        job = ImportJob.objects.get(user=self.user)
        self.assertTrue(job.wipe_existing)
        self.assertTrue(job.file_path.startswith(f"nirvana_imports/{self.user.id}/"))
        self.assertTrue(default_storage.exists(job.file_path))
        mock_task.delay.assert_called_once_with(
            job.file_path, self.user.id, True, job.id
        )

    @patch("nirvana.views.run_nirvana_import")
    def test_post_rejected_while_an_import_is_active(self, mock_task):
        ImportJob.objects.create(
            user=self.user, file_path="busy.json", status=ImportJob.Status.RUNNING
        )
        export = SimpleUploadedFile("export.json", b"[]")
        response = self.client.post(self.url, {"file": export})

        self.assertRedirects(response, self.url)
        self.assertEqual(ImportJob.objects.count(), 1)
        mock_task.delay.assert_not_called()

    @patch("nirvana.views.run_nirvana_import")
    def test_post_invalid_file_shows_error_and_creates_nothing(self, mock_task):
        export = SimpleUploadedFile("export.json", b"not json")
        response = self.client.post(self.url, {"file": export})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "not a valid JSON file")
        self.assertFalse(ImportJob.objects.exists())
        mock_task.delay.assert_not_called()

    def test_recent_imports_only_show_own_jobs(self):
        other = User.objects.create_user(username="stranger", password="pass")
        ImportJob.objects.create(
            user=other, file_path="theirs.json", status=ImportJob.Status.SUCCESS
        )
        mine = ImportJob.objects.create(
            user=self.user, file_path="mine.json", status=ImportJob.Status.SUCCESS
        )
        response = self.client.get(self.url)
        self.assertEqual(list(response.context["jobs"]), [mine])
        self.assertIsNone(response.context["active_job"])

    def test_recent_imports_capped_at_limit(self):
        for _ in range(12):
            ImportJob.objects.create(
                user=self.user, file_path="x.json", status=ImportJob.Status.SUCCESS
            )
        response = self.client.get(self.url)
        self.assertEqual(len(response.context["jobs"]), 10)
        self.assertContains(response, "Showing last 10 items")

    def test_recent_imports_note_hidden_when_below_limit(self):
        ImportJob.objects.create(
            user=self.user, file_path="x.json", status=ImportJob.Status.SUCCESS
        )
        response = self.client.get(self.url)
        self.assertNotContains(response, "Showing last")

    def test_active_job_hides_upload_form(self):
        ImportJob.objects.create(
            user=self.user, file_path="x.json", status=ImportJob.Status.RUNNING
        )
        response = self.client.get(self.url)
        self.assertContains(response, "Import in progress")
        self.assertNotContains(response, "Start import")


class TestNirvanaImportJobStatusView(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="pass")
        self.other = User.objects.create_user(username="other", password="pass")
        self.client = Client()
        self.client.login(username="owner", password="pass")
        self.job = ImportJob.objects.create(
            user=self.user, file_path="x.json", status=ImportJob.Status.RUNNING
        )
        self.url = reverse("nirvana_import_job_status", args=[self.job.id])

    def test_running_job_partial_polls(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'hx-trigger="every 2s"')
        self.assertNotIn("HX-Refresh", response)

    def test_running_job_shows_relative_heartbeat(self):
        self.job.heartbeat = timezone.now() - timedelta(seconds=30)
        self.job.save()
        response = self.client.get(self.url)
        self.assertContains(response, "Last seen: 30\xa0seconds ago")

    def test_finished_job_partial_stops_polling(self):
        self.job.status = ImportJob.Status.SUCCESS
        self.job.save()
        response = self.client.get(self.url)
        self.assertNotContains(response, "hx-trigger")

    def test_finished_job_triggers_page_refresh_for_htmx_polling(self):
        self.job.status = ImportJob.Status.SUCCESS
        self.job.save()
        response = self.client.get(self.url, headers={"HX-Request": "true"})
        self.assertEqual(response["HX-Refresh"], "true")

    def test_other_users_job_is_404(self):
        self.client.login(username="other", password="pass")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)


@override_settings(CACHES=CACHES_OVERRIDE, STORAGES=STORAGES_OVERRIDE)
class TestNirvanaImportJobCancelView(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="pass")
        self.client = Client()
        self.client.login(username="owner", password="pass")
        self.job = ImportJob.objects.create(
            user=self.user, file_path="x.json", status=ImportJob.Status.RUNNING
        )
        self.url = reverse("nirvana_import_job_cancel", args=[self.job.id])

    def test_owner_can_request_cancellation(self):
        response = self.client.post(self.url)
        self.assertRedirects(response, reverse("nirvana_import"))
        self.assertTrue(is_cancellation_requested(self.job.pk))

    def test_other_users_job_is_404(self):
        User.objects.create_user(username="intruder", password="pass")
        self.client.login(username="intruder", password="pass")
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 404)
        self.assertFalse(is_cancellation_requested(self.job.pk))

    def test_finished_job_is_not_flagged(self):
        self.job.status = ImportJob.Status.SUCCESS
        self.job.save()
        response = self.client.post(self.url)
        self.assertRedirects(response, reverse("nirvana_import"))
        self.assertFalse(is_cancellation_requested(self.job.pk))

    def test_get_is_not_allowed(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_stale_job_is_cleaned_up_immediately(self):
        from datetime import timedelta

        from django.core.files.base import ContentFile

        from nirvana.models import heartbeat_max_age

        path = default_storage.save("nirvana_imports/stale.json", ContentFile(b"[]"))
        ImportJob.objects.filter(pk=self.job.pk).update(
            file_path=path,
            heartbeat=timezone.now() - heartbeat_max_age() - timedelta(minutes=1),
        )
        response = self.client.post(self.url)

        self.assertRedirects(response, reverse("nirvana_import"))
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, ImportJob.Status.CANCELLED)
        self.assertFalse(default_storage.exists(path))
        # No flag left behind: there is no worker to read it.
        self.assertFalse(is_cancellation_requested(self.job.pk))
