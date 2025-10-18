import sys
from datetime import datetime

from celery.signals import worker_init
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import autoreload

from task_processor.celery import app as celery_app


class Command(BaseCommand):
    help = "Starts a Celery worker instance with auto-reloading for development."

    # Validation is called explicitly each time the worker instance is reloaded.
    requires_system_checks = []
    suppressed_base_arguments = {"--verbosity", "--traceback"}

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-checks",
            action="store_true",
            help="Skip system checks.",
        )
        parser.add_argument(
            "--loglevel",
            choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "FATAL"),
            type=str.upper,  # Transforms user input to uppercase.
            default="INFO",
        )

    def handle(self, *args, **options):
        autoreload.run_with_reloader(self.run_worker, **options)

    def run_worker(self, **options):
        # If an exception was silenced in ManagementUtility.execute in order
        # to be raised in the child process, raise it now.
        autoreload.raise_last_exception()

        if not options["skip_checks"]:
            self.stdout.write("Performing system checks...\n\n")
            self.check(display_num_errors=True)

        # Need to check migrations here, so can't use the
        # requires_migrations_check attribute.
        self.check_migrations()

        # Print Django info to console when the worker initializes.
        worker_init.connect(self.on_worker_init)

        # Start the Celery worker.
        # > run celery -A batch_processor --skip-checks worker -l info
        celery_app.worker_main(
            [
                "--app",
                "task_processor",
                "--skip-checks",
                "worker",
                "--queues",
                "reminders,celery",
                "--loglevel",
                options["loglevel"],
            ]
        )

    def on_worker_init(self, sender, **kwargs):
        quit_command = "CTRL-BREAK" if sys.platform == "win32" else "CONTROL-C"

        now = datetime.now().strftime("%B %d, %Y - %X")
        version = self.get_version()
        print(
            f"{now}\n"
            f"Django version {version}, using settings {settings.SETTINGS_MODULE!r}\n"
            f"Quit the worker instance with {quit_command}.",
            file=self.stdout,
        )
