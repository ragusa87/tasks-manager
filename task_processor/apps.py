from django.apps import AppConfig


class TaskProcessorConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'task_processor'
    verbose_name = 'Task Processor'

    def ready(self):
        # Import models to ensure they're registered
        pass