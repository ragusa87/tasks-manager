"""Reusable Nirvana JSON import logic.

Shared by the ``nirvana_import`` management command and the Celery task
(``nirvana.tasks.run_nirvana_import``). Callers decide about wrapping
``import_items`` in a transaction: the CLI keeps the whole import atomic,
while the Celery task runs without an outer transaction so that progress
rows written by its callback are visible to the polling web process.
"""

from dataclasses import dataclass
from datetime import datetime
from datetime import timezone as dt_timezone

from django.db import transaction
from django.utils import timezone

from task_processor.constants import GTDEnergy, GTDStatus, Priority
from task_processor.models import Area, Context, Item
from task_processor.models.base_models import Tag

PHASE_WIPING = "Wiping existing data"
PHASE_CREATING = "Creating items"
PHASE_PARENTS = "Linking parents"
PHASE_TAGS = "Assigning tags"

# Passes of import_items, in execution order (PHASE_WIPING runs before, if asked).
IMPORT_PHASES = [PHASE_CREATING, PHASE_PARENTS, PHASE_TAGS]


@dataclass
class ImportResult:
    created: int
    updated: int

    @property
    def total(self):
        return self.created + self.updated


class NirvanaImporter:
    """Imports a parsed Nirvana export (list of dicts) for a user.

    ``log`` receives human-readable messages (the command passes
    ``self.stdout.write``). ``progress`` receives ``(phase, current, total)``
    for every processed item; throttling is the callback's responsibility.
    """

    def __init__(self, log=None, progress=None):
        self.log = log or (lambda msg: None)
        self.progress = progress or (lambda phase, current, total: None)

    def dry_run_analysis(self, nirvana_items):
        """Analyze the export file without importing. Returns a stats dict."""
        states = {}
        types = {}
        has_parent = 0
        has_tags = 0
        completed = 0

        for item in nirvana_items:
            state = item.get("state", 0)
            states[state] = states.get(state, 0) + 1

            item_type = item.get("type", 0)
            types[item_type] = types.get(item_type, 0) + 1

            if item.get("parentid"):
                has_parent += 1

            if item.get("tags", "").strip(","):
                has_tags += 1

            if item.get("completed", 0) > 0:
                completed += 1

        return {
            "total": len(nirvana_items),
            "completed": completed,
            "has_parent": has_parent,
            "has_tags": has_tags,
            "states": states,
            "types": types,
        }

    def import_items(self, nirvana_items, user):
        """Import items into the system"""
        created_count = 0
        updated_count = 0
        tags_cache = {}
        total = len(nirvana_items)

        # First pass: Create all items without relationships
        item_mapping = {}

        for index, nirvana_item in enumerate(nirvana_items):
            self.progress(PHASE_CREATING, index + 1, total)

            # Skip deleted items
            if nirvana_item.get("deleted", 0) > 0:
                continue

            gtd_item, was_created = self.create_item_from_nirvana(nirvana_item, user)
            if gtd_item:
                item_mapping[nirvana_item["id"]] = gtd_item
                if was_created:
                    created_count += 1
                else:
                    updated_count += 1

        # Second pass: Handle parent relationships
        for index, nirvana_item in enumerate(nirvana_items):
            self.progress(PHASE_PARENTS, index + 1, total)

            if nirvana_item.get("deleted", 0) > 0:
                continue

            parent_id = nirvana_item.get("parentid")
            if parent_id:
                child_item = item_mapping.get(nirvana_item["id"])
                # Parents usually come from the same export; only fall back to
                # the DB for items imported in a previous run. The lookup MUST
                # stay scoped to the user: nirvana ids are only unique within
                # one account's export.
                parent_item = item_mapping.get(parent_id)
                if parent_item is None:
                    parent_item = Item.objects.filter(
                        nirvana_id=str(parent_id), user=user
                    ).first()
                if child_item and parent_item:
                    child_item.parent = parent_item
                    child_item.save()

        # Third pass: Handle tags as contexts
        for index, nirvana_item in enumerate(nirvana_items):
            self.progress(PHASE_TAGS, index + 1, total)

            if nirvana_item.get("deleted", 0) > 0:
                continue

            tags = nirvana_item.get("tags", "").strip(",")
            if tags:
                gtd_item = item_mapping.get(nirvana_item["id"])
                if gtd_item:
                    self.assign_tags(gtd_item, tags, user, tags_cache)

        self.log(f"Created: {created_count}, Updated: {updated_count}")
        return ImportResult(created=created_count, updated=updated_count)

    def create_item_from_nirvana(self, nirvana_item, user):
        """Convert a Nirvana item to a GTD Item"""
        # Map Nirvana state to GTD status
        state = nirvana_item.get("state", 0)
        status = self.map_nirvana_state_to_gtd_status(
            state, nirvana_item.get("type", 0)
        )

        # Create timestamps
        created_ts = nirvana_item.get("created", 0)
        updated_ts = nirvana_item.get("updated", 0)
        completed_ts = nirvana_item.get("completed", 0)

        created_at = (
            datetime.fromtimestamp(created_ts, tz=dt_timezone.utc)
            if created_ts
            else timezone.now()
        )
        updated_at = (
            timezone.make_aware(datetime.fromtimestamp(updated_ts))
            if updated_ts
            else created_at
        )
        completed_at = (
            timezone.make_aware(datetime.fromtimestamp(completed_ts))
            if completed_ts
            else None
        )

        # Truncate title if too long (max 1024 chars for Item.title field)
        title = nirvana_item.get("name", "Untitled")
        if len(title) > 1024:
            title = title[:1021] + "..."

        # Create the item using nirvana_id as unique identifier
        item, created = Item.objects.update_or_create(
            nirvana_id=str(nirvana_item["id"]),
            user=user,
            defaults={
                "title": title,
                "description": nirvana_item.get("note", ""),
                "status": status,
                "priority": Priority.NORMAL,  # Nirvana doesn't have explicit priority
                "created_at": created_at,
                "updated_at": updated_at,
                "is_completed": (completed_ts > 0),
                "completed_at": completed_at,
                "waiting_for_person": nirvana_item.get("waitingfor", ""),
                "energy": self._map_nirvana_energy(nirvana_item.get("energy", "")),
            },
        )

        # Handle due date
        duedate = nirvana_item.get("duedate", "")
        if duedate:
            try:
                # Nirvana stores dates as timestamps
                due_ts = int(duedate)
                item.due_date = timezone.make_aware(datetime.fromtimestamp(due_ts))
            except (ValueError, TypeError):
                pass

        item.save()
        return item, created

    def map_nirvana_state_to_gtd_status(self, state, nirvana_type):
        """Map Nirvana states to GTD statuses"""
        # Nirvana type mapping:
        # type 0: regular tasks/actions
        # type 1: projects (containers for tasks)
        # type 2: reference items (information/notes)
        # type 3: reference areas/folders (containers for reference items)

        # For reference items, always use REFERENCE status regardless of state
        if nirvana_type == 2:
            return GTDStatus.REFERENCE

        # For reference areas/folders (type 3), also use REFERENCE status
        # These are containers for reference items, not projects
        if nirvana_type == 3:
            return GTDStatus.REFERENCE

        # For projects (type 1), map to PROJECT status when active, otherwise use state mapping
        if nirvana_type == 1:
            # Active projects
            if state in [0, 1, 4, 11]:  # inbox, active, project, someday_maybe
                return GTDStatus.PROJECT
            elif state == 7:  # completed
                return GTDStatus.COMPLETED
            else:
                return GTDStatus.PROJECT

        # For regular tasks/actions (type 0), use state-based mapping
        state_mapping = {
            0: GTDStatus.INBOX,
            1: GTDStatus.NEXT_ACTION,
            2: GTDStatus.REFERENCE,
            4: GTDStatus.NEXT_ACTION,  # Convert project state to next action for tasks
            7: GTDStatus.COMPLETED,
            10: GTDStatus.WAITING_FOR,
            11: GTDStatus.SOMEDAY_MAYBE,
        }

        return state_mapping.get(state, GTDStatus.INBOX)

    def assign_tags(self, item, tags_string, user, tags_cache):
        """Assign contexts based on Nirvana tags"""
        tag_names = [tag.strip() for tag in tags_string.split(",") if tag.strip()]

        for tag_name in tag_names:
            # Get or create context
            if tag_name not in tags_cache:
                context, created = Tag.objects.get_or_create(
                    name=tag_name,
                    user=user,
                )
                tags_cache[tag_name] = context

            item.tags.add(tags_cache[tag_name])

    def delete_existing_data(self, user, dry_run=False):
        """Delete all existing Items, Areas, and Contexts for the user"""
        # Count existing data before deletion
        items_count = Item.objects.filter(user=user).count()
        areas_count = Area.objects.filter(user=user).count()
        tags_count = Tag.objects.filter(user=user).count()
        contexts_count = Context.objects.filter(user=user).count()

        self.log(f"Found existing data for {user.username} to delete:")
        self.log(f"  Items: {items_count}")
        self.log(f"  Areas: {areas_count}")
        self.log(f"  Tags: {tags_count}")
        self.log(f"  Contexts: {contexts_count}")
        if dry_run:
            self.log("  - Dry run")
            return

        if items_count > 0 or areas_count > 0 or contexts_count > 0:
            # Delete all user data
            with transaction.atomic():
                # Delete Items (this will cascade to related objects)
                deleted_items = Item.objects.filter(user=user).delete()
                # Delete Areas
                deleted_areas = Area.objects.filter(user=user).delete()
                # Delete Contexts
                deleted_contexts = Context.objects.filter(user=user).delete()
                # Delete Tags
                deleted_tags = Tag.objects.filter(user=user).delete()

            self.log(
                f"Deleted {deleted_items[0]} items, {deleted_areas[0]} areas, {deleted_tags[0]} tags"
                f"and {deleted_contexts[0]} contexts for user {user.username}"
            )
        else:
            self.log("No existing data to delete.")

    @staticmethod
    def _map_nirvana_energy(level):
        state_mapping = {
            1: GTDEnergy.LOW,
            2: GTDEnergy.MEDIUM,
            3: GTDEnergy.HIGH,
        }
        return state_mapping.get(level, None)
