from django.core.management.base import BaseCommand, CommandError

from task_processor.models import Item


class Command(BaseCommand):
    help = 'List available transitions for a given item'

    def add_arguments(self, parser):
        parser.add_argument(
            'item_id',
            type=int,
            help='ID of the item to check transitions for'
        )
        # Option "--available-only"
        parser.add_argument(
            '--available-only',
            action='store_true',
            help='Show only transitions available from the current status'
        )


    def handle(self, *args, **options):
        item_id = options['item_id']

        try:
            item = Item.objects.get(id=item_id)
        except Item.DoesNotExist:
            raise CommandError(f'Item with id "{item_id}" does not exist')

        # Display item information
        self.stdout.write(f"\nItem: {item.title}")
        self.stdout.write(f"Current Status: {item.get_status_display()}")
        self.stdout.write(f"User: {item.user.username}")
        if item.parent:
            self.stdout.write(f"Parent Project: {item.parent.title}")
            self.stdout.write(f"Parent Project Status: {item.parent.get_status_display()}")


        self.stdout.write("-" * 50)

        # Get available transitions
        transitions = item.get_available_transitions() if options['available_only'] else item.get_all_transitions()
        label = "Available transitions" if options['available_only'] else "All transitions"

        if not transitions:
            self.stdout.write(f"\nNo transitions available from current status: {item.get_status_display()}")
            return

        self.stdout.write(f"\n{label} ({len(transitions)}):")
        for i, transition in enumerate(transitions, 1):
            self.stdout.write(
                f"{i}. {transition['icon']}  {transition['label']} ({transition['name']}) : {transition['source']} -> {transition['target']}"
            )