from django.conf import settings
from django.core.management.base import BaseCommand

from task_processor.mail_inbox.dsn import parse_dsn
from task_processor.mail_inbox.engines import build_engine


class Command(BaseCommand):
    help = (
        "Run the email-to-task inbox listener. "
        "The engine is configured by the EMAIL_INBOX_DSN setting."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--host", default=None, help="Override the host from the DSN"
        )
        parser.add_argument(
            "--port", type=int, default=None, help="Override the port from the DSN"
        )

    def handle(self, *args, **options):
        dsn = parse_dsn(settings.EMAIL_INBOX_DSN)
        engine = build_engine(dsn, host=options["host"], port=options["port"])
        self.stdout.write(
            self.style.SUCCESS(f"Starting mail inbox engine ({dsn.scheme})")
        )
        engine.run()
