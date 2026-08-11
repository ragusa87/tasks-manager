from django.contrib import admin

from .models import ImportJob


@admin.register(ImportJob)
class ImportJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "status",
        "phase",
        "progress_current",
        "progress_total",
        "wipe_existing",
        "heartbeat",
        "created_at",
    )
    list_filter = ("status", "wipe_existing")
    readonly_fields = [
        field.name for field in ImportJob._meta.fields if field.name != "id"
    ]

    def has_add_permission(self, request):
        return False
