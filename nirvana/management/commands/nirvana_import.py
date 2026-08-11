import json
import os

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from nirvana.importer import NirvanaImporter


class Command(BaseCommand):
    help = "Import Nirvana export JSON file into the GTD system"

    def add_arguments(self, parser):
        parser.add_argument(
            "filename", type=str, help="Path to the Nirvana export JSON file"
        )
        parser.add_argument(
            "user",
            type=str,
            default="user1@example.com",
            help="Username to assign imported items to ",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be imported without actually importing",
        )
        parser.add_argument(
            "--delete",
            action="store_true",
            help="Delete all existing Items and Areas for the user before importing",
        )

    def handle(self, *args, **options):
        filename = options["filename"]

        # Check if file exists
        if not os.path.exists(filename):
            raise CommandError(f'File "{filename}" does not exist.')

        try:
            user = User.objects.get(username=options["user"])
        except User.DoesNotExist:
            raise CommandError(f'User "{options["user"]}" does not exist.')

        self.stdout.write(f"Importing items for user: {user.username}")

        # Load JSON file
        try:
            with open(filename, "r", encoding="utf-8") as f:
                nirvana_items = json.load(f)
        except json.JSONDecodeError as e:
            raise CommandError(f"Invalid JSON file: {e}")
        except Exception as e:
            raise CommandError(f"Error reading file: {e}")

        self.stdout.write(f"Found {len(nirvana_items)} items in export file")

        importer = NirvanaImporter(log=self.stdout.write)

        if options["dry_run"]:
            stats = importer.dry_run_analysis(nirvana_items)
            self.stdout.write(self.style.WARNING("=== DRY RUN ANALYSIS ==="))
            self.stdout.write(f"Total items: {stats['total']}")
            self.stdout.write(f"Completed items: {stats['completed']}")
            self.stdout.write(f"Items with parent: {stats['has_parent']}")
            self.stdout.write(f"Items with tags: {stats['has_tags']}")
            self.stdout.write(f"States distribution: {stats['states']}")
            self.stdout.write(f"Types distribution: {stats['types']}")
            return

        # Delete existing data if requested
        if options["delete"]:
            importer.delete_existing_data(user, dry_run=options["dry_run"])

        # Import items
        with transaction.atomic():
            result = importer.import_items(nirvana_items, user)

        self.stdout.write(
            self.style.SUCCESS(f"Successfully imported {result.total} items")
        )
