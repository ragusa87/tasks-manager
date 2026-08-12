from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import FormView, TemplateView, View

from .cancellation import clear_cancellation, request_cancellation
from .forms import NirvanaImportForm
from .models import ImportJob
from .tasks import run_nirvana_import


@method_decorator(login_required, name="dispatch")
class NirvanaImportView(FormView):
    """Upload a Nirvana JSON export and start the import in Celery."""

    form_class = NirvanaImportForm
    template_name = "nirvana/import.html"
    success_url = reverse_lazy("nirvana_import")
    recent_jobs_limit = 10

    def form_valid(self, form):
        user = self.request.user
        # The form is hidden while a job runs, but that doesn't stop a
        # double-submit or a second tab: two concurrent imports (especially
        # with wipe) would interleave arbitrarily.
        if ImportJob.objects.filter(
            user=user, status__in=ImportJob.UNFINISHED_STATUSES
        ).exists():
            messages.error(self.request, "An import is already in progress.")
            return redirect("nirvana_import")
        file_path = default_storage.save(
            f"nirvana_imports/{user.id}/{uuid4().hex}.json",
            form.cleaned_data["file"],
        )
        wipe = form.cleaned_data["wipe_existing"]
        job = ImportJob.objects.create(
            user=user, file_path=file_path, wipe_existing=wipe
        )
        run_nirvana_import.delay(file_path, user.id, wipe, job.id)
        messages.success(self.request, "Import started.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        jobs = ImportJob.objects.filter(user=self.request.user)
        active_job = jobs.filter(status__in=ImportJob.UNFINISHED_STATUSES).first()
        context["active_job"] = active_job
        if active_job:
            jobs = jobs.exclude(pk=active_job.pk)
        context["jobs"] = jobs[: self.recent_jobs_limit]
        context["recent_jobs_limit"] = self.recent_jobs_limit
        return context


@method_decorator(login_required, name="dispatch")
class NirvanaImportJobCancelView(View):
    """Flag a pending/running import for cancellation; the worker picks the
    flag up between progress writes. Only the job's owner can cancel it."""

    def post(self, request, job_id):
        job = get_object_or_404(ImportJob, pk=job_id, user=request.user)
        if job.is_finished:
            messages.info(request, "This import has already finished.")
        elif job.is_stale:
            # The worker went silent: no one would ever read a cancel flag,
            # so clean the job up right away instead (like the periodic
            # cleanup task would, but without the wait). Compare-and-set so a
            # worker or the cleanup task finishing the job right now wins.
            cleaned = ImportJob.objects.filter(
                pk=job.pk,
                status__in=ImportJob.UNFINISHED_STATUSES,
                heartbeat=job.heartbeat,
            ).update(status=ImportJob.Status.CANCELLED)
            if cleaned:
                job.delete_upload()
                clear_cancellation(job.pk)
                messages.info(
                    request, "The import was stalled — it has been cleaned up."
                )
            else:
                messages.info(request, "The import just changed state; check below.")
        else:
            request_cancellation(job.pk)
            messages.info(request, "Cancellation requested — stopping the import.")
        return redirect("nirvana_import")


@method_decorator(login_required, name="dispatch")
class NirvanaImportJobStatusView(TemplateView):
    """HTMX polling endpoint rendering the job-status partial."""

    template_name = "nirvana/partials/job_status.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["job"] = get_object_or_404(
            ImportJob, pk=self.kwargs["job_id"], user=self.request.user
        )
        return context

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        # Only the partial is swapped while polling, so the surrounding
        # "Import in progress" card would stay stale forever: once the job
        # finishes, reload the whole page (upload form + recent imports).
        job = response.context_data["job"]
        if job.is_finished and request.headers.get("HX-Request"):
            response["HX-Refresh"] = "true"
        return response
