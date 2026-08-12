from django.urls import path

from .views import (
    NirvanaImportJobCancelView,
    NirvanaImportJobStatusView,
    NirvanaImportView,
)

urlpatterns = [
    path("", NirvanaImportView.as_view(), name="nirvana_import"),
    path(
        "jobs/<int:job_id>/status/",
        NirvanaImportJobStatusView.as_view(),
        name="nirvana_import_job_status",
    ),
    path(
        "jobs/<int:job_id>/cancel/",
        NirvanaImportJobCancelView.as_view(),
        name="nirvana_import_job_cancel",
    ),
]
