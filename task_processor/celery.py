"""
Celery app configuration for the GTD task processing system.
"""

import os

from celery import Celery
from django.conf import settings  # noqa

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.development')

# Create the Celery app
app = Celery('tasks-proto')

# Use Django settings for configuration
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks from all installed Django apps
app.autodiscover_tasks()

# Configure periodic tasks (beat schedule)
from celery.schedules import crontab

app.conf.beat_schedule = {
    'check-reminders-every-30-minutes': {
        'task': 'task_processor.tasks.check_reminders',
        'schedule': crontab(minute='*/30'),
        'options': {'queue': 'reminders'}
    },
}

# Default queue configuration
app.conf.task_default_queue = 'reminders'
app.conf.task_routes = {
    'task_processor.tasks.check_reminders': {'queue': 'reminders'},
    'task_processor.tasks.send_reminder': {'queue': 'reminders'},
}

