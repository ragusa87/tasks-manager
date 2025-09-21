from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from task_processor.models import Item
from task_processor.models.base_models import Area, Tag


class Command(BaseCommand):
    help = 'Migrate items from a tag to an area for a specific user'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            type=str,
            required=True,
            help='Username of the user to perform migration for'
        )
        parser.add_argument(
            '--tag',
            type=str,
            required=True,
            help='Name of the tag to migrate from'
        )
        parser.add_argument(
            '--area',
            type=str,
            required=True,
            help='Name of the area to migrate to'
        )
        parser.add_argument(
            '--create-area',
            action='store_true',
            help='Create the area if it does not exist'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without actually doing it'
        )
        parser.add_argument(
            '--delete-tag',
            action='store_true',
            help='Delete the tag after migration if it has no remaining items'
        )

    def handle(self, *args, **options):
        username = options['user']
        tag_name = options['tag']
        area_name = options['area']
        create_area = options['create_area']
        dry_run = options['dry_run']
        delete_tag = options['delete_tag']

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f'User "{username}" does not exist.')

        # Get the tag
        try:
            tag = Tag.objects.get(name=tag_name, user=user)
        except Tag.DoesNotExist:
            raise CommandError(f'Tag "{tag_name}" does not exist for user "{username}".')

        # Get or create the area
        area = None
        try:
            area = Area.objects.get(name=area_name, user=user)
            self.stdout.write(f'Found existing area: "{area_name}"')
        except Area.DoesNotExist:
            if create_area:
                if not dry_run:
                    area = Area.objects.create(
                        name=area_name,
                        user=user,
                        description=f'Area created from tag "{tag_name}" migration'
                    )
                self.stdout.write(
                    self.style.SUCCESS(f'{"Would create" if dry_run else "Created"} area: "{area_name}"')
                )
            else:
                raise CommandError(
                    f'Area "{area_name}" does not exist for user "{username}". '
                    'Use --create-area to create it automatically.'
                )

        # Find all items with this tag
        items_with_tag = Item.objects.filter(
            user=user,
            tags=tag
        ).select_related('area').prefetch_related('tags')

        item_count = items_with_tag.count()

        if item_count == 0:
            self.stdout.write(
                self.style.WARNING(f'No items found with tag "{tag_name}" for user "{username}".')
            )
            return

        self.stdout.write(f'Found {item_count} items with tag "{tag_name}"')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No changes will be made'))

        # Show items that will be affected
        for item in items_with_tag:
            current_area = item.area.name if item.area else "No area"
            action = "Would update" if dry_run else "Updating"
            self.stdout.write(
                f'  {action} item "{item.title}" (ID: {item.id}) - '
                f'Current area: {current_area} -> New area: {area_name}'
            )

        if not dry_run:
            # Perform the migration in a transaction
            with transaction.atomic():
                updated_count = 0

                for item in items_with_tag:
                    # Set the area
                    item.area = area
                    # Remove the tag
                    item.save()
                    item.tags.remove(tag)
                    updated_count += 1

                self.stdout.write(
                    self.style.SUCCESS(f'Successfully updated {updated_count} items.')
                )

                # Check if tag should be deleted
                if delete_tag:
                    remaining_items = Item.objects.filter(tags=tag).count()
                    if remaining_items == 0:
                        tag.delete()
                        self.stdout.write(
                            self.style.SUCCESS(f'Deleted tag "{tag_name}" (no remaining items).')
                        )
                    else:
                        self.stdout.write(
                            self.style.WARNING(
                                f'Tag "{tag_name}" still has {remaining_items} items. Not deleting.'
                            )
                        )
        else:
            # Dry run summary
            if delete_tag:
                remaining_items = Item.objects.filter(tags=tag).exclude(id__in=items_with_tag).count()
                if remaining_items == 0:
                    self.stdout.write(f'Would delete tag "{tag_name}" (no remaining items)')
                else:
                    self.stdout.write(
                        f'Would NOT delete tag "{tag_name}" (has {remaining_items} other items)'
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f'{"Would complete" if dry_run else "Completed"} migration of '
                f'{item_count} items from tag "{tag_name}" to area "{area_name}"'
            )
        )