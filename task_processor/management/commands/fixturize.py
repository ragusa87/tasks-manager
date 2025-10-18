import random
from datetime import timedelta

from django.contrib.auth.models import User
from django.core import management
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.utils import timezone

from task_processor.constants import (
    GTDConfig,
    GTDDuration,
    GTDEnergy,
    GTDStatus,
    Priority,
    ReviewType,
)
from task_processor.models import Area, Context, Item, Review, Tag


class Command(BaseCommand):
    help = "Generate sample data for development/demo environment"

    def add_arguments(self, parser):
        parser.add_argument(
            "--users",
            type=int,
            default=2,
            help="Number of users to create (default: 2)",
        )
        parser.add_argument(
            "--items-per-user",
            type=int,
            default=50,
            help="Number of items per user (default: 50)",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing data before generating new data",
        )

    def run_migrations(self):
        self.stdout.write("Running migrations... ")
        from io import StringIO

        management.call_command("migrate", "--noinput", stdout=StringIO())

    def handle(self, *args, **options):
        if options["clear"]:
            self.stdout.write("Clearing existing data...")
            self.clear_data()

        self.run_migrations()

        self.stdout.write("Generating sample data...")

        with transaction.atomic():
            users = self.create_users(options["users"])
            for user in users:
                self.stdout.write(f"Creating data for user: {user.username}")
                self.create_contexts_areas_and_tags(user)
                self.create_items(user, options["items_per_user"])
                self.create_reviews(user)

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully created sample data for {len(users)} users"
            )
        )

    def reset_sequence(self, model):
        table = model._meta.db_table
        pk = model._meta.pk.column
        seq = f"{table}_{pk}_seq"

        with connection.cursor() as cursor:
            cursor.execute(f"SELECT COALESCE(MAX({pk}), 0) + 1 FROM {table}")
            next_val = cursor.fetchone()[0]
            cursor.execute(f"ALTER SEQUENCE {seq} RESTART WITH {next_val}")

    def clear_data(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
            all_tables = [row[0] for row in cursor.fetchall()]

            # Exclude system tables
            tables_to_drop = [
                t
                for t in all_tables
                if t not in {"spatial_ref_sys"} and not t.startswith("temp_")
            ]
            for table in tables_to_drop:
                cursor.execute(f'DROP TABLE "{table}" CASCADE')

    def create_users(self, count):
        """Create sample users"""
        users = []
        for i in range(count):
            username = f"user{i + 1}"
            email = f"user{i + 1}@example.com"

            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": email,
                    "first_name": "User",
                    "last_name": f"{i + 1}",
                    "is_active": True,
                },
            )
            if created:
                user.set_password("password")
                user.save()
            users.append(user)
        return users

    def create_contexts_areas_and_tags(self, user):
        """Create contexts, areas, and tags for user"""
        # Create contexts
        for context_name in GTDConfig.DEFAULT_CONTEXTS:
            Context.objects.update_or_create(
                name=context_name,
                user=user,
                defaults={"description": f"Default context: {context_name}"},
            )

        # Create areas
        Area.create_defaults_for_user(user)

        # Create sample tags
        sample_tags = [
            "transport",
            "read",
            "watch",
            "phone-call",
            "meeting",
            "creative",
            "planning",
            "admin",
            "review",
            "personal",
            "work",
            "learning",
            "health",
            "finance",
        ]
        for tag_name in sample_tags:
            Tag.objects.get_or_create(name=tag_name, user=user)

    def create_items(self, user, count):
        """Create various GTD items for user"""
        contexts = list(Context.objects.filter(user=user))
        areas = list(Area.objects.filter(user=user))
        tags = list(Tag.objects.filter(user=user))

        # Templates for different types of items
        inbox_items = [
            "Review quarterly budget report",
            "Call dentist to schedule appointment",
            "Research vacation destinations",
            "Organize home office desk",
            "Update LinkedIn profile",
            "Read book recommendation from colleague",
            "Plan weekend family activity",
            "Submit expense reports",
            "Schedule car maintenance",
            "Backup computer files",
        ]

        project_templates = [
            "Plan company retreat",
            "Renovate kitchen",
            "Learn Python programming",
            "Organize family reunion",
            "Launch new product",
            "Write annual report",
            "Implement new CRM system",
            "Plan garden makeover",
            "Organize photo collection",
            "Build home automation system",
        ]

        next_action_templates = [
            "Email client about project status",
            "Buy groceries for dinner party",
            "Review and approve team proposals",
            "Update project documentation",
            "Schedule team meeting",
            "Prepare presentation slides",
            "Call insurance company",
            "Fix broken door handle",
            "Research competitor pricing",
            "Test new software feature",
        ]

        waiting_for_templates = [
            ("Approval from manager", "Manager Smith"),
            ("Medical test results", "Dr. Johnson"),
            ("Quote from contractor", "ABC Construction"),
            ("Feedback on proposal", "Client XYZ"),
            ("Payment from client", "Invoice #123"),
            ("Equipment delivery", "Supplier Corp"),
            ("Legal review completion", "Legal Dept"),
            ("Software license renewal", "IT Department"),
            ("Interview scheduling", "HR Team"),
            ("Budget approval", "Finance Team"),
        ]

        someday_maybe_templates = [
            "Learn to play guitar",
            "Visit Japan",
            "Write a novel",
            "Start a podcast",
            "Learn photography",
            "Build a treehouse",
            "Learn Spanish",
            "Start a blog",
            "Take cooking classes",
            "Learn woodworking",
        ]

        # Generate items with realistic distribution
        items_created = 0

        # Create projects first (15% of items)
        project_count = int(count * 0.15)
        projects = []
        for i in range(project_count):
            project = self.create_project_item(
                user,
                random.choice(project_templates) + f" {i + 1}",
                contexts,
                areas,
                tags,
            )
            projects.append(project)
            items_created += 1

        # Create next actions (40% of items)
        next_action_count = int(count * 0.40)
        for i in range(next_action_count):
            # Some next actions belong to projects
            parent = (
                random.choice(projects) if projects and random.random() < 0.3 else None
            )
            self.create_next_action_item(
                user,
                random.choice(next_action_templates)
                + (f" {i + 1}" if not parent else ""),
                contexts,
                areas,
                tags,
                parent,
            )
            items_created += 1

        # Create inbox items (20% of items)
        inbox_count = int(count * 0.20)
        for i in range(inbox_count):
            self.create_inbox_item(
                user, random.choice(inbox_items) + f" {i + 1}", contexts, areas, tags
            )
            items_created += 1

        # Create waiting for items (10% of items)
        waiting_count = int(count * 0.10)
        for i in range(waiting_count):
            title, person = random.choice(waiting_for_templates)
            self.create_waiting_for_item(
                user, title + f" {i + 1}", person, contexts, areas, tags
            )
            items_created += 1

        # Create someday/maybe items (10% of items)
        someday_count = int(count * 0.10)
        for i in range(someday_count):
            self.create_someday_maybe_item(
                user,
                random.choice(someday_maybe_templates) + f" {i + 1}",
                contexts,
                areas,
                tags,
            )
            items_created += 1

        # Fill remaining with random items
        remaining = count - items_created
        for i in range(remaining):
            self.create_random_item(user, contexts, areas, tags, i + 1)

    def create_project_item(self, user, title, contexts, areas, tags):
        """Create a project item"""
        project = Item.objects.create(
            title=title,
            description=f"Multi-step project: {title}",
            status=GTDStatus.PROJECT,
            priority=random.choice([Priority.NORMAL, Priority.HIGH]),
            user=user,
            area=random.choice(areas) if random.random() < 0.95 else None,
            due_date=self.random_future_date() if random.random() < 0.6 else None,
            estimated_duration=random.choice(list(GTDDuration))
            if random.random() < 0.7
            else None,
            energy=random.choice(list(GTDEnergy)) if random.random() < 0.6 else None,
        )

        # Add contexts after creation (ManyToMany field)
        if random.random() < 0.85 and contexts:
            # Usually add 1-2 contexts
            selected_contexts = random.sample(
                contexts, min(random.randint(1, 2), len(contexts))
            )
            project.contexts.set(selected_contexts)

        # Add tags after creation (ManyToMany field)
        if random.random() < 0.6 and tags:
            # Sometimes add 1-3 tags
            selected_tags = random.sample(tags, min(random.randint(1, 3), len(tags)))
            project.tags.set(selected_tags)

        return project

    def create_next_action_item(self, user, title, contexts, areas, tags, parent=None):
        """Create a next action item"""
        item = Item.objects.create(
            title=title,
            description=f"Actionable task: {title}",
            status=GTDStatus.NEXT_ACTION,
            priority=random.choice(list(Priority)),
            user=user,
            parent=parent,
            area=random.choice(areas) if random.random() < 0.85 else None,
            due_date=self.random_future_date() if random.random() < 0.4 else None,
            estimated_duration=random.choice(list(GTDDuration))
            if random.random() < 0.8
            else None,
            energy=random.choice(list(GTDEnergy)) if random.random() < 0.7 else None,
            is_completed=random.random() < 0.2,  # 20% completed
        )

        # Add contexts after creation (ManyToMany field)
        if random.random() < 0.95 and contexts:
            # Almost always add 1 context, sometimes 2
            selected_contexts = random.sample(
                contexts, min(random.randint(1, 2), len(contexts))
            )
            item.contexts.set(selected_contexts)

        # Add tags after creation (ManyToMany field)
        if random.random() < 0.8 and tags:
            # Frequently add 1-2 tags
            selected_tags = random.sample(tags, min(random.randint(1, 2), len(tags)))
            item.tags.set(selected_tags)

        # Set completion date for completed items
        if item.is_completed:
            item.completed_at = self.random_past_datetime()
            item.status = GTDStatus.COMPLETED
            item.save()

        return item

    def create_inbox_item(self, user, title, contexts, areas, tags):
        """Create an inbox item"""
        item = Item.objects.create(
            title=title,
            description=f"Unprocessed item: {title}",
            status=GTDStatus.INBOX,
            priority=Priority.NORMAL,
            user=user,
            # Inbox items occasionally get assigned area during capture
            area=random.choice(areas) if random.random() < 0.3 else None,
        )

        # Add contexts after creation (ManyToMany field)
        if random.random() < 0.2 and contexts:
            # Rarely add contexts to inbox items (some people pre-categorize)
            selected_contexts = random.sample(contexts, min(1, len(contexts)))
            item.contexts.set(selected_contexts)

        # Add tags after creation (ManyToMany field)
        if random.random() < 0.3 and tags:
            # Rarely add tags to inbox items
            selected_tags = random.sample(tags, min(1, len(tags)))
            item.tags.set(selected_tags)

        return item

    def create_waiting_for_item(self, user, title, person, contexts, areas, tags):
        """Create a waiting for item"""
        item = Item.objects.create(
            title=title,
            description=f"Waiting for: {title}",
            status=GTDStatus.WAITING_FOR,
            priority=random.choice([Priority.NORMAL, Priority.HIGH]),
            user=user,
            area=random.choice(areas) if random.random() < 0.75 else None,
            waiting_for_person=person,
            date_requested=self.random_past_date(days=30),
            follow_up_date=self.random_future_date(days=14),
        )

        # Add contexts after creation (ManyToMany field)
        if random.random() < 0.7 and contexts:
            # Usually add contexts for waiting items
            selected_contexts = random.sample(contexts, min(1, len(contexts)))
            item.contexts.set(selected_contexts)

        # Add tags after creation (ManyToMany field)
        if random.random() < 0.4 and tags:
            # Sometimes add tags to waiting items
            selected_tags = random.sample(tags, min(random.randint(1, 2), len(tags)))
            item.tags.set(selected_tags)

        return item

    def create_someday_maybe_item(self, user, title, contexts, areas, tags):
        """Create a someday/maybe item"""
        item = Item.objects.create(
            title=title,
            description=f"Someday/maybe: {title}",
            status=GTDStatus.SOMEDAY_MAYBE,
            priority=random.choice([Priority.LOW, Priority.NORMAL]),
            user=user,
            area=random.choice(areas) if random.random() < 0.95 else None,
            last_reviewed=self.random_past_date(days=180)
            if random.random() < 0.7
            else None,
            review_frequency_days=random.choice([30, 60, 90, 180]),
        )

        # Add contexts after creation (ManyToMany field)
        if random.random() < 0.6 and contexts:
            # Sometimes add contexts to someday/maybe items
            selected_contexts = random.sample(
                contexts, min(random.randint(1, 2), len(contexts))
            )
            item.contexts.set(selected_contexts)

        # Add tags after creation (ManyToMany field)
        if random.random() < 0.5 and tags:
            # Sometimes add tags to someday/maybe items
            selected_tags = random.sample(tags, min(random.randint(1, 2), len(tags)))
            item.tags.set(selected_tags)

        return item

    def create_random_item(self, user, contexts, areas, tags, index):
        """Create a random item of any type"""
        status = random.choice(
            [
                GTDStatus.NEXT_ACTION,
                GTDStatus.PROJECT,
                GTDStatus.REFERENCE,
                GTDStatus.COMPLETED,
            ]
        )

        item = Item.objects.create(
            title=f"Random item {index}",
            description=f"Random item description {index}",
            status=status,
            priority=random.choice(list(Priority)),
            user=user,
            area=random.choice(areas) if random.random() < 0.8 else None,
            due_date=self.random_future_date() if random.random() < 0.3 else None,
            is_completed=status == GTDStatus.COMPLETED,
        )

        # Add contexts after creation (ManyToMany field)
        if random.random() < 0.75 and contexts:
            # Usually add 1-2 contexts
            selected_contexts = random.sample(
                contexts, min(random.randint(1, 2), len(contexts))
            )
            item.contexts.set(selected_contexts)

        # Add tags after creation (ManyToMany field)
        if random.random() < 0.5 and tags:
            # Sometimes add tags to random items
            selected_tags = random.sample(tags, min(random.randint(1, 2), len(tags)))
            item.tags.set(selected_tags)

        return item

    def create_reviews(self, user):
        """Create sample review data"""
        # Create some past reviews
        for i in range(4):  # Last 4 weeks
            review_date = timezone.now().date() - timedelta(weeks=i + 1)
            Review.objects.get_or_create(
                user=user,
                review_type=ReviewType.WEEKLY,
                review_date=review_date,
                defaults=dict(
                    notes=f"Weekly review - Week {i + 1}",
                    inbox_items_processed=random.randint(5, 15),
                    projects_reviewed=random.randint(2, 8),
                    next_actions_identified=random.randint(3, 12),
                    someday_maybe_reviewed=random.randint(1, 5),
                    waiting_for_followed_up=random.randint(0, 3),
                ),
            )

        # Create a monthly review
        review_date = timezone.now().date() - timedelta(days=30)
        Review.objects.get_or_create(
            user=user,
            review_type=ReviewType.MONTHLY,
            review_date=review_date,
            defaults=dict(
                notes="Monthly review - Comprehensive system review",
                inbox_items_processed=random.randint(20, 40),
                projects_reviewed=random.randint(8, 15),
                next_actions_identified=random.randint(15, 30),
                someday_maybe_reviewed=random.randint(5, 15),
                waiting_for_followed_up=random.randint(2, 8),
            ),
        )

    def random_future_date(self, days=30):
        """Generate a random future date within specified days"""
        random_days = random.randint(1, days)
        return timezone.now() + timedelta(days=random_days)

    def random_past_date(self, days=30):
        """Generate a random past date within specified days"""
        random_days = random.randint(1, days)
        return timezone.now().date() - timedelta(days=random_days)

    def random_past_datetime(self, days=30):
        """Generate a random past datetime within specified days"""
        random_days = random.randint(1, days)
        random_hours = random.randint(0, 23)
        random_minutes = random.randint(0, 59)
        return timezone.now() - timedelta(
            days=random_days, hours=random_hours, minutes=random_minutes
        )
