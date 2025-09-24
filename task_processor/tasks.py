"""
Celery tasks for the GTD task processing system.
"""

import logging
from datetime import datetime

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .constants import GTDStatus
from .models.item import Item
from .signals import reminder_due

logger = logging.getLogger(__name__)


@shared_task(bind=True, name='task_processor.tasks.check_reminders')
def check_reminders(self):
    """
    Periodic task that runs every 30 minutes to check for due reminders.

    Queries for items where remind_at is due and triggers reminder signals.
    Only processes active items (not completed) with actionable status.
    """
    now = timezone.now()

    # Query items where reminders are due
    due_items = Item.objects.filter(
        remind_at__lte=now,
        remind_at__isnull=False,
        is_completed=False,
        status__in=[GTDStatus.NEXT_ACTION, GTDStatus.PROJECT]
    ).select_related('user')

    reminder_count = 0
    error_count = 0

    for item in due_items:
        try:
            with transaction.atomic():
                # Send the reminder signal
                reminder_due.send(
                    sender=Item,
                    item=item,
                    reminder_time=now
                )
                reminder_count += 1
                logger.info(f"Sent reminder signal for item: {item.title} (ID: {item.id})")

        except Exception as e:
            error_count += 1
            logger.error(f"Error sending reminder for item {item.id}: {str(e)}")

    result = {
        'at': now,
        'processed_at': now.isoformat(),
        'reminders_sent': reminder_count,
        'errors': error_count,
        'total_items_checked': due_items.count()
    }

    logger.info(f"Reminder check completed: {result}")
    return result


@shared_task(bind=True, name='task_processor.tasks.send_reminder')
def send_reminder(self, item_id, reminder_time_str):
    """
    Task to send an individual reminder notification.
    This is called by the reminder service after receiving the reminder_due signal.
    """
    try:
        item = Item.objects.get(id=item_id)
        reminder_time = datetime.fromisoformat(reminder_time_str.replace('Z', '+00:00'))

        # This will be implemented by the reminder service
        # For now, just log the reminder
        logger.info(f"Processing reminder for item: {item.title} (ID: {item.id}) at {reminder_time}")
        reminder_due.send(
            sender=Item,
            item=item,
            reminder_time=reminder_time
        )
        return {
            'success': True,
            'item_id': item_id,
            'item_title': item.title,
            'reminder_time': reminder_time_str
        }

    except Item.DoesNotExist:
        logger.error(f"Item with ID {item_id} not found for reminder")
        return {
            'success': False,
            'error': f"Item with ID {item_id} not found",
            'item_id': item_id
        }
    except Exception as e:
        logger.error(f"Error sending reminder for item {item_id}: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'item_id': item_id
        }