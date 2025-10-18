"""
Django management command to manually trigger reminder checking.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from task_processor.tasks import check_reminders as check_reminders_task


class Command(BaseCommand):
    help = "Check for due reminders and send reminder signals"

    def add_arguments(self, parser):
        parser.add_argument(
            "--async",
            action="store_true",
            help="Run the task asynchronously using Celery",
        )
        parser.add_argument(
            "--verbose", action="store_true", help="Show detailed output"
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS(f"Starting reminder check at {timezone.now()}")
        )

        try:
            if options["async"]:
                # Run asynchronously using Celery
                result = check_reminders_task.delay()
                self.stdout.write(
                    self.style.SUCCESS(f"Task queued with ID: {result.id}")
                )
            else:
                # Run synchronously
                result = check_reminders_task.apply()
                task_result = result.result

                if options["verbose"]:
                    self.stdout.write(self.style.SUCCESS("Reminder check completed!"))
                    self.stdout.write(
                        f"Processed at: {task_result.get('processed_at', 'Unknown')}"
                    )
                    self.stdout.write(
                        f"Reminders sent: {task_result.get('reminders_sent', 0)}"
                    )
                    self.stdout.write(f"Errors: {task_result.get('errors', 0)}")
                    self.stdout.write(
                        f"Total items checked: {task_result.get('total_items_checked', 0)}"
                    )
                else:
                    reminders_sent = task_result.get("reminders_sent", 0)
                    errors = task_result.get("errors", 0)

                    if reminders_sent > 0:
                        self.stdout.write(
                            self.style.SUCCESS(f"✓ Sent {reminders_sent} reminder(s)")
                        )

                    if errors > 0:
                        self.stdout.write(
                            self.style.ERROR(f"✗ {errors} error(s) occurred")
                        )

                    if reminders_sent == 0 and errors == 0:
                        self.stdout.write(
                            self.style.WARNING("No reminders were due at this time")
                        )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Error running reminder check: {str(e)}")
            )
            raise
