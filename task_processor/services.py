"""
Django signals for GTD task processing system.
"""
import logging
from datetime import datetime
from typing import Optional

from dateutil.rrule import rrulestr
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models.functions import TruncSecond
from django.urls import reverse
from django.utils import timezone

from .constants import GTDConfig
from .models.item import Item, ItemReminderLog

logger = logging.getLogger(__name__)

class ReminderService:
    """
    Service class to handle reminder processing and email notifications.
    """

    @staticmethod
    def send_reminder_email(item: Item) -> bool:
        """
        Send a reminder email for the given item.

        Args:
            item: The Item instance to send a reminder for

        Returns:
            Tuple of (success: bool, error_message: str or None)
        """
        try:
            subject = f"Reminder: {item.title}"
            message = ReminderService._build_email_message(item)
            recipient_email = item.user.email

            if not recipient_email:
                return False

            send_mail(
                subject=subject,
                message=message,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com'),
                recipient_list=[recipient_email],
                fail_silently=False
            )

            logger.info(f"Reminder email sent successfully for item {item.id} to {recipient_email}")
            return True

        except Exception as e:
            error_msg = f"Failed to send reminder email: {str(e)}"
            logger.error(error_msg)
            raise e

    @staticmethod
    def _build_email_message(item: Item) -> str:
        """Build the email message content for a reminder."""
        message_lines = [
            "This is a reminder for your GTD item:",
            "",
            f"Title: {item.title}",
            f"Status: {item.get_status_display()}",
            f"Priority: {item.get_priority_display()}",
        ]

        if item.due_date:
            message_lines.extend(["", f"Due Date: {item.due_date.strftime('%Y-%m-%d %H:%M')}"])

        if item.area:
            message_lines.extend(["", f"Area: {item.area.name}"])

        if item.contexts.exists():
            contexts = ", ".join([ctx.name for ctx in item.contexts.all()])
            message_lines.extend(["", f"Contexts: {contexts}"])

        domain = settings.FRONTEND_URL.rstrip("/")
        url = f"{domain}" + reverse("dashboard") + f"?q=id:{item.pk}"
        message_lines.extend(["", f"URL: {url}"])

        message_lines.extend([
            "",
            "Take action on this item when you have the time and context.",
            "",
            "Best regards,",
        ])

        return "\n".join(message_lines)

    @staticmethod
    def _calculate_next_reminder(item: Item) -> Optional[datetime]:
        """
        Calculate the next reminder time based on the item's RRULE.

        Args:
            item: The Item instance

        Returns:
            Next reminder datetime or None if no recurrence
        """
        if not item.rrule:
            return None

        try:
            # Parse the RRULE
            rrule = rrulestr(item.rrule)

            # Get the next occurrence after the current remind_at time
            # If remind_at is None, use current time
            start_time = item.remind_at or timezone.now()

            # Convert to naive datetime for rrule calculation if needed
            if timezone.is_aware(start_time):
                start_naive = timezone.localtime(start_time).replace(tzinfo=None)
            else:
                start_naive = start_time

            # Get the next occurrence
            next_occurrence = rrule.after(start_naive, inc=False)

            if next_occurrence:
                # Convert to Django timezone-aware datetime
                if next_occurrence.tzinfo is None:
                    next_occurrence = timezone.make_aware(next_occurrence)

                logger.info(f"Next reminder for item {item.id} calculated: {next_occurrence}")
                return next_occurrence

            return None

        except Exception as e:
            logger.error(f"Error calculating next reminder for item {item.id}: {str(e)}")
            return None

    def _process_reminder(self, item: Item, reminded_at: datetime) -> ItemReminderLog:
        """
        Process a reminder for an item. This includes:
        1. Creating a reminder log entry
        2. Attempting to send the email
        3. Updating the next reminder time if successful
        4. Handling retries if failed

        Args:
            item: The Item to send reminder for
            reminder_at: When the reminder was triggered

        Returns:
            ItemReminderLog instance
        """
        with transaction.atomic():
            # Create the initial log entry
            created = False
            log_entry = ItemReminderLog.objects.annotate(
                reminded_sec=TruncSecond('reminded_at')
            ).filter(item=item, reminded_sec=reminded_at.replace(microsecond=0)).first()
            if not log_entry:
                created = True
                log_entry = ItemReminderLog.objects.create(
                    item=item,
                    reminded_at=reminded_at,
                )

            if not log_entry.active:
                logger.info(f"Skiping inactive reminder {item.id}")

                return log_entry

            # Try to send the reminder
            try:
                self.send_reminder_email(item)

                # Email sent successfully - calculate next reminder
                next_reminder = self._calculate_next_reminder(item)
                item.remind_at = next_reminder
                item.save(update_fields=['remind_at'])

                return log_entry


            except Exception as e:
                error_message = f"Exception during email send: {str(e)}"
                logger.error(error_message)

                # Email failed - log the error and check retry logic
                log_entry.error = error_message
                if not created:
                    log_entry.nb_retry = log_entry.nb_retry + 1

                # Check if we should continue retrying
                if log_entry.nb_retry >= GTDConfig.MAX_REMINDER_THRESHOLD:
                    log_entry.active = False
                    logger.warning(f"Max retry threshold reached for item {item.id}. Disabling further attempts.")
                else:
                    logger.info(f"Reminder failed for item {item.id}. Will retry later. Attempt {log_entry.nb_retry}")

                log_entry.save()

            return log_entry

    def handle_reminder_due(self, item, reminder_at, **kwargs) -> ItemReminderLog:
        """
        Signal handler for when a reminder is due.
        This processes the reminder using the ReminderService.
        """
        logger.info(f"Received reminder_due signal for item {item.id}: {item.title}")

        try:
            reminder_log = self._process_reminder(item, reminder_at)

            if reminder_log.is_success:
                logger.info(f"Reminder processed successfully for item {item.id}")
            else:
                logger.warning(f"Reminder processing failed for item {item.id}: {reminder_log.error}")
            return reminder_log
        except Exception as e:
            logger.error(f"Error in reminder_due signal handler for item {item.id}: {str(e)}")
            raise e


reminder_service = ReminderService()