"""
Django management command to manually send a reminder for a specific item.
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from task_processor.models.item import Item
from task_processor.tasks import send_reminder as send_reminder_task


class Command(BaseCommand):
    help = 'Send a reminder for a specific item'

    def add_arguments(self, parser):
        parser.add_argument(
            'item_id',
            type=int,
            help='ID of the item to send reminder for'
        )
        parser.add_argument(
            '--async',
            action='store_true',
            help='Run the task asynchronously using Celery'
        )
        parser.add_argument(
            '--reminder-time',
            type=str,
            help='Custom reminder time (ISO format), defaults to now'
        )

    def item_details(self, item: Item):
        # Show item details
        self.stdout.write('\nItem details:')
        self.stdout.write(f'  Title: {item.title}')
        self.stdout.write(f'  Status: {item.get_status_display()}')
        self.stdout.write(f'  User: {item.user.username} ({item.user.email})')

        if item.remind_at:
            self.stdout.write(f'  Next scheduled reminder: {item.remind_at}')

        if item.rrule:
            self.stdout.write(f'  Recurrence pattern: {item.rrule}')

    def handle(self, *args, **options):
        item_id = options['item_id']

        # Validate item exists
        try:
            item = Item.objects.get(id=item_id)
        except Item.DoesNotExist:
            raise CommandError(f'Item with ID {item_id} does not exist')

        # Parse reminder time
        self.item_details(item)
        self.stdout.write('')

        if options['reminder_time']:
            try:
                from datetime import datetime
                reminder_time = datetime.fromisoformat(options['reminder_time'].replace('Z', '+00:00'))
                if timezone.is_naive(reminder_time):
                    reminder_time = timezone.make_aware(reminder_time)
            except ValueError:
                raise CommandError(
                    'Invalid reminder time format. Use ISO format like "2024-01-15T14:30:00" or "2024-01-15T14:30:00Z"'
                )
        else:
            reminder_time = timezone.now()

        try:
            if options['async']:
                # Run asynchronously using Celery
                result = send_reminder_task.delay(item_id, reminder_time.isoformat())
                self.stdout.write(
                    self.style.SUCCESS(f'Task queued with ID: {result.id}')
                )
                return

            # Run synchronously
            result = send_reminder_task.apply(args=[item_id, reminder_time.isoformat()])
            task_result = result.result

            if task_result.get('success', False):
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✓ Reminder sent successfully for item "{task_result.get("item_title", "Unknown")}"'
                    )
                )
            else:
                error = task_result.get('error', 'Unknown error')
                self.stdout.write(
                    self.style.ERROR(f'✗ Failed to send reminder: {error}')
                )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error sending reminder: {str(e)}')
            )
            raise

