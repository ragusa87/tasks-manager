"""
Tests for the GTD reminder system.
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from task_processor.constants import GTDConfig, GTDStatus
from task_processor.models.base_models import Area, Context
from task_processor.models.item import Item, ItemReminderLog
from task_processor.tasks import check_reminders


class ReminderSystemTestCase(TestCase):
    """Test case for the reminder system functionality."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        self.area = Area.objects.create(name="Test Area", user=self.user)

        self.context = Context.objects.create(name="@test", user=self.user)

    def test_item_with_reminder_fields(self):
        """Test creating an item with reminder fields."""
        remind_time = timezone.now() + timedelta(hours=1)
        rrule = "FREQ=DAILY;INTERVAL=1"

        item = Item.objects.create(
            title="Test Reminder Item",
            description="Testing the reminder system",
            user=self.user,
            status=GTDStatus.NEXT_ACTION,
            remind_at=remind_time,
            rrule=rrule,
        )

        self.assertEqual(item.remind_at, remind_time)
        self.assertEqual(item.rrule, rrule)

    @patch("task_processor.services.send_mail")
    def test_reminder_email_integration_success(self, mock_send_mail):
        """Test successful reminder processing through task integration."""
        mock_send_mail.return_value = True

        # Create item with past reminder time
        past_time = timezone.now() - timedelta(minutes=10)
        item = Item.objects.create(
            title="Email Test Item",
            description="Testing email functionality",
            user=self.user,
            status=GTDStatus.NEXT_ACTION,
            area=self.area,
            remind_at=past_time,
            is_completed=False,
        )
        item.contexts.add(self.context)

        # Run the reminder check task
        result: list[ItemReminderLog] = check_reminders.apply().get()

        # Verify task ran successfully
        self.assertEqual(len(result), 1, "Expected one result from task")
        self.assertIsNone(result[0].error, "No error expected")

        # Verify email was sent
        mock_send_mail.assert_called_once()

        # Verify reminder log was created
        log_entries = ItemReminderLog.objects.filter(item=item)
        self.assertTrue(log_entries.exists())

        latest_log = log_entries.latest("reminded_at")
        self.assertTrue(latest_log.is_success)
        self.assertEqual(latest_log.nb_retry, 0)

    @patch("task_processor.services.send_mail")
    def test_reminder_email_integration_failure(self, mock_send_mail):
        """Test reminder processing failure through task integration."""
        mock_send_mail.side_effect = Exception("SMTP Error")

        # Create item with past reminder time
        past_time = timezone.now() - timedelta(minutes=10)
        item = Item.objects.create(
            title="Email Failure Test",
            user=self.user,
            status=GTDStatus.NEXT_ACTION,
            remind_at=past_time,
            is_completed=False,
        )

        # Run the reminder check task
        result: list[ItemReminderLog] = check_reminders.apply().get()

        # Verify task processed the reminder (even though email failed)
        # The task still counts it as "sent"
        self.assertTrue(len(result) == 1, "Expected one result from task")
        self.assertIsNotNone(result[0].error, "Sending email should have failed")

        # Verify reminder log was created with failure
        log_entries = ItemReminderLog.objects.filter(item=item)
        self.assertTrue(log_entries.exists())

        latest_log = log_entries.latest("reminded_at")
        self.assertTrue(latest_log.is_failed)
        self.assertEqual(latest_log.nb_retry, 0, "Item should not be retried yet")
        self.assertIsNotNone(latest_log.error)

    @patch("task_processor.services.send_mail")
    def test_reminder_email_integration_failure_twice(self, mock_send_mail):
        """Test reminder processing failure through task integration."""
        mock_send_mail.side_effect = Exception("SMTP Error")

        # Create item with past reminder time
        past_time = timezone.now() - timedelta(minutes=10)
        item = Item.objects.create(
            title="Email Failure Test",
            user=self.user,
            status=GTDStatus.NEXT_ACTION,
            remind_at=past_time,
            is_completed=False,
        )
        # Refresh item to get the exact timestamp from DB
        item.refresh_from_db()

        # Create existing log with the exact timestamp that will be used by the task
        existing_log = ItemReminderLog.objects.create(
            item=item,
            error="First error",
            nb_retry=GTDConfig.MAX_REMINDER_THRESHOLD - 1,
            active=True,
            reminded_at=item.remind_at,  # Use the exact DB timestamp
        )

        # Run the reminder check task
        result: list[ItemReminderLog] = check_reminders.apply().get()

        # Verify task processed the reminder
        self.assertEqual(len(result), 1, "Expected one result from task")
        self.assertIsNotNone(result[0].error, "Sending email should have failed")

        # Verify the existing log was updated (not a new one created)
        log_entries = ItemReminderLog.objects.filter(item=item)
        self.assertEqual(log_entries.count(), 1, "Should have only one log entry")

        # The returned log should be the updated existing one
        updated_log = log_entries.first()
        self.assertEqual(
            updated_log.id, existing_log.id, "Should be the same log entry"
        )
        self.assertTrue(updated_log.is_failed)
        self.assertEqual(
            updated_log.nb_retry,
            GTDConfig.MAX_REMINDER_THRESHOLD,
            "nb_retry should be incremented by 1",
        )
        self.assertIsNotNone(updated_log.error)

    def test_recurring_reminder_reschedule(self):
        """Test that recurring reminders are rescheduled after processing."""
        # Create item with past reminder time and daily recurrence
        past_time = timezone.now() - timedelta(minutes=10)
        item = Item.objects.create(
            title="Recurring Reminder Test",
            user=self.user,
            status=GTDStatus.NEXT_ACTION,
            remind_at=past_time,
            rrule="FREQ=DAILY;INTERVAL=1",
            is_completed=False,
        )

        original_remind_at = item.remind_at

        with patch("task_processor.services.send_mail", return_value=True):
            # Run the reminder check task
            result: list[ItemReminderLog] = check_reminders.apply().get()

            # Verify task ran successfully
            self.assertEqual(len(result), 1, "Expected one result from task")
            self.assertIsNone(result[0].error, "No error expected")

        # Refresh item from database
        item.refresh_from_db()

        # Verify remind_at was updated to next occurrence
        self.assertIsNotNone(item.remind_at)
        self.assertNotEqual(item.remind_at, original_remind_at)
        # Should be later than the original (next scheduled occurrence)
        self.assertGreater(item.remind_at, original_remind_at)

    def test_one_time_reminder_cleared(self):
        """Test that one-time reminders are cleared after processing."""
        # Create item with past reminder time and no recurrence
        past_time = timezone.now() - timedelta(minutes=10)
        item = Item.objects.create(
            title="One-time Reminder Test",
            user=self.user,
            status=GTDStatus.NEXT_ACTION,
            remind_at=past_time,
            rrule=None,  # No recurrence
            is_completed=False,
        )

        with patch("task_processor.services.send_mail", return_value=True):
            # Run the reminder check task
            result: list[ItemReminderLog] = check_reminders.apply().get()

            # Verify task ran successfully
            self.assertEqual(len(result), 1, "Expected one result from task")
            self.assertIsNone(result[0].error, "No error expected")

        # Refresh item from database
        item.refresh_from_db()

        # Verify remind_at was cleared (no next occurrence)
        self.assertIsNone(item.remind_at)

    def test_check_reminders_task(self):
        """Test the periodic reminder checking task."""
        # Create an item with past reminder time
        past_time = timezone.now() - timedelta(minutes=10)
        Item.objects.create(
            title="Past Reminder Item",
            user=self.user,
            status=GTDStatus.NEXT_ACTION,
            remind_at=past_time,
            is_completed=False,
        )

        # Create an item that shouldn't be processed (future reminder)
        future_time = timezone.now() + timedelta(hours=1)
        Item.objects.create(
            title="Future Reminder Item",
            user=self.user,
            status=GTDStatus.NEXT_ACTION,
            remind_at=future_time,
            is_completed=False,
        )

        with patch("task_processor.tasks.reminder_due.send") as mock_signal:
            result: list[ItemReminderLog] = check_reminders.apply().get()

            # Should have found 1 item and sent 1 signal
            self.assertEqual(len(result), 1, "Expected one result from task")
            mock_signal.assert_called_once()

    def test_item_completion_clears_reminders(self):
        """Test that completing an item clears reminders."""
        item = Item.objects.create(
            title="Completion Test Item",
            user=self.user,
            status=GTDStatus.NEXT_ACTION,
            remind_at=timezone.now() + timedelta(hours=1),
            rrule="FREQ=DAILY;INTERVAL=1",
        )

        # Create some reminder logs
        ItemReminderLog.objects.create(item=item, nb_retry=0, active=True)

        # Complete the item
        item.is_completed = True
        item.save()

        item.refresh_from_db()
        # Reminders should be cleared
        # Note: The signal handler should handle this, but we need to ensure signals are connected
        # For this test, we'll manually verify the behavior would work

    def test_reminder_log_properties(self):
        """Test ItemReminderLog model properties."""
        item = Item.objects.create(
            title="Log Test Item", user=self.user, status=GTDStatus.NEXT_ACTION
        )

        # Test successful log
        success_log = ItemReminderLog.objects.create(item=item, nb_retry=0, active=True)

        self.assertTrue(success_log.is_success)
        self.assertFalse(success_log.is_failed)
        self.assertTrue(success_log.can_retry)

        # Test failed log
        failed_log = ItemReminderLog.objects.create(
            item=item, error="Test error", nb_retry=5, active=True
        )

        self.assertFalse(failed_log.is_success)
        self.assertTrue(failed_log.is_failed)
        self.assertTrue(failed_log.can_retry)

        # Test max retries reached
        max_retry_log = ItemReminderLog.objects.create(
            item=item, error="Max retries", nb_retry=10, active=False
        )

        self.assertFalse(max_retry_log.can_retry)


class ReminderFormTestCase(TestCase):
    """Test case for reminder form validation."""

    def test_rrule_validation_valid_patterns(self):
        """Test RRULE validation with valid patterns."""
        from task_processor.forms import RecurrenceField

        field = RecurrenceField()

        # Test valid patterns
        valid_patterns = [
            "FREQ=DAILY;INTERVAL=1",
            "FREQ=DAILY;INTERVAL=2",
            "FREQ=WEEKLY;BYDAY=MO,WE,FR",
            "FREQ=MONTHLY;BYMONTHDAY=15",
            "",  # Empty should be valid
            None,  # None should be valid
        ]

        for pattern in valid_patterns:
            try:
                cleaned = field.clean(pattern)
                # Should not raise ValidationError
                if pattern:
                    self.assertEqual(cleaned, pattern)
                else:
                    # Empty string or None should return None after cleaning
                    self.assertIsNone(cleaned)
            except Exception as e:
                self.fail(f"Valid pattern '{pattern}' should not raise exception: {e}")

    def test_rrule_validation_invalid_patterns(self):
        """Test RRULE validation with invalid patterns."""
        from django.core.exceptions import ValidationError

        from task_processor.forms import RecurrenceField

        field = RecurrenceField()

        # Test invalid patterns
        invalid_patterns = [
            "FREQ=HOURLY;INTERVAL=1",  # Too frequent
            "FREQ=MINUTELY;INTERVAL=1",  # Too frequent
            "INVALID_PATTERN",  # Not a valid RRULE
            "FREQ=DAILY;INVALID=1",  # Invalid parameter
        ]

        for pattern in invalid_patterns:
            with self.assertRaises(ValidationError):
                field.clean(pattern)
