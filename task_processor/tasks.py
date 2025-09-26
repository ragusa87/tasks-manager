"""
Celery tasks for the GTD task processing system.
"""

import logging
from datetime import datetime

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .constants import GTDStatus
from .models.item import Item, ItemReminderLog
from .signals import reminder_due

logger = logging.getLogger(__name__)


@shared_task(bind=True, name='task_processor.tasks.check_reminders')
def check_reminders(self) -> list[ItemReminderLog]:
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
        status__in=[GTDStatus.NEXT_ACTION, GTDStatus.PROJECT],
        user__is_active=True
    ).select_related('user')

    responses = []

    for item in due_items:

        # Send the reminder signal
        raw = None
        try:
            with transaction.atomic():
               raw = reminder_due.send(
                    sender=Item,
                    item=item,
                    reminder_at=item.remind_at
                )

               response: ItemReminderLog|None = raw[0][1]


            if response is None:
                logger.warning(f"No response from reminder_due signal for item {item.id}")
                continue

            responses.append(response)
        except IndexError as e:
            logger.error(f"Error processing reminder for item {item.id}: No response from signal: {str(e)}")
            continue

    return responses



@shared_task(bind=True, name='task_processor.tasks.send_reminder')
def send_reminder(self, item_id, reminder_time_str):
    """
    Task to send an individual reminder notification.
    This is called by the reminder service after receiving the reminder_due signal.
    """
    try:
        item = Item.objects.get(id=item_id)
        reminder_at = datetime.fromisoformat(reminder_time_str.replace('Z', '+00:00'))

        # This will be implemented by the reminder service
        # For now, just log the reminder
        logger.info(f"Processing reminder for item: {item.title} (ID: {item.id}) at {reminder_at}")
        reminder_due.send(
            sender=Item,
            item=item,
            reminder_at=reminder_at
        )
        return {
            'success': True,
            'item_id': item_id,
            'item_title': item.title,
            'reminder_time_str': reminder_time_str
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