from django.contrib import admin, messages
from unfold.admin import ModelAdmin

from task_processor.models import ApiKey


@admin.register(ApiKey)
class ApiKeyAdmin(ModelAdmin):
    list_display = ("name", "user", "prefix", "is_active", "created_at", "last_used_at")
    list_filter = ("is_active",)
    readonly_fields = ("prefix", "created_at", "last_used_at")
    fields = ("user", "name", "is_active", "prefix", "created_at", "last_used_at")

    def save_model(self, request, obj, form, change):
        if not change:
            raw_key = obj.assign_new_key()
            messages.warning(
                request,
                f"API key (copy it now, it is shown only once): {raw_key}",
            )
        super().save_model(request, obj, form, change)
