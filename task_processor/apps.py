from django.apps import AppConfig


class TaskProcessorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "task_processor"
    verbose_name = "Task Processor"

    def ready(self):
        # Connect the post_save/pre_delete receivers. Without this import the
        # signals were only active in processes that import tasks.py (the
        # celery worker), so e.g. completing an item from the web never
        # cleared its reminder/recurrence.
        from . import signals  # noqa: F401
