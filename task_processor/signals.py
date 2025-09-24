"""
Django signals for GTD task processing system.
"""
import logging

from django.db.models.signals import post_save, pre_delete
from django.dispatch import Signal, receiver

from .models.item import Item, ItemReminderLog
from .services import reminder_service

logger = logging.getLogger(__name__)

# Custom signal sent when a reminder is due
reminder_due = Signal()

@receiver(post_save, sender=Item)
def handle_item_status_change(sender, instance, created, **kwargs):
    """
    Signal handler for Item post_save.
    Clears reminders when an item is completed or archived.
    """
    if not created:  # Only for updates, not new items
        # If item is completed or archived, clear reminders and remove reminder logs
        if instance.is_completed or instance.status in ['completed', 'cancelled']:
            if instance.remind_at:
                logger.info(f"Clearing reminder for completed/cancelled item {instance.id}")
                instance.remind_at = None
                instance.rrule = None
                # Save without triggering the signal again
                Item.objects.filter(id=instance.id).update(
                    remind_at=None,
                    rrule=None
                )

            # Remove associated reminder logs
            deleted_count = ItemReminderLog.objects.filter(item=instance).delete()[0]
            if deleted_count > 0:
                logger.info(f"Removed {deleted_count} reminder logs for completed item {instance.id}")

        # If remind_at is manually cleared, remove all associated logs
        elif not instance.remind_at and hasattr(instance, '_previous_remind_at'):
            if instance._previous_remind_at:  # Had a previous remind_at value
                logger.info(f"Remind_at cleared for item {instance.id}, removing reminder logs")
                deleted_count = ItemReminderLog.objects.filter(item=instance).delete()[0]
                if deleted_count > 0:
                    logger.info(f"Removed {deleted_count} reminder logs for item {instance.id}")


@receiver(pre_delete, sender=Item)
def handle_item_deletion(sender, instance, **kwargs):
    """
    Signal handler for Item pre_delete.
    Removes all associated ItemReminderLog entries when an item is deleted.
    Note: This is handled automatically by the CASCADE foreign key, but we log it.
    """
    reminder_log_count = ItemReminderLog.objects.filter(item=instance).count()
    if reminder_log_count > 0:
        logger.info(f"Item {instance.id} being deleted. Will cascade delete {reminder_log_count} reminder logs.")

@receiver(reminder_due)
def handle_reminder_due(*args, **kwargs):
    reminder_service.handle_reminder_due(*args, **kwargs)