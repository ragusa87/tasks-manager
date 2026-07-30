# gtd/batch.py
"""
Generic batch-actions framework, mirroring the ItemFlow transition pattern:
one method per action on a per-model helper class, decorated with metadata,
and the UI / execution wired dynamically from the class (see BatchActionView
and templates/partials/batch_bar.html).

A selection is stateless and travels in the POST payload:
- ``ids``: explicit primary keys (checkboxes on the current page), or
- ``select_all=1`` + ``q``: "every object matching this search", rebuilt
  server-side via ``apply_query()`` so huge selections never post id lists,
  minus ``excluded_ids`` (rows unticked after a select-all, Gmail-style).
"""

from django.db import transaction
from django.db.models import Q
from django.utils.module_loading import import_string
from django.utils.translation import gettext_lazy as _

from task_processor.models import Item
from task_processor.models.base_models import Area, Tag


def batch_action(
    label, sprite=None, form_class=None, position=0, applicable=None, description=None
):
    """
    Decorator marking a BatchActions method as a batch action.

    Args:
        label: Human-readable action name (shown on buttons and in the modal).
        sprite: Sprite icon name (see sprites/).
        form_class: Optional Django form for extra input (can be a string path,
            resolved lazily like @requires_form on transitions).
        position: Ordering, mirroring ItemTransitionsBag (higher first).
        applicable: Optional ``callable(actions, queryset) -> queryset``
            restricting which selected objects the action may touch. The view
            previews the applicable/skipped split and only modifies the
            applicable subset.
        description: Optional translatable text shown in the confirm modal
            (and as the action button's tooltip) explaining what the action
            does — in particular its applicability rule, so users understand
            why some selected objects are skipped.
    """

    def decorator(func):
        func._batch_action = {
            "name": func.__name__,
            "label": label,
            "sprite": sprite,
            "form_class": form_class,
            "position": position,
            "applicable": applicable,
            "description": description,
        }
        return func

    return decorator


class BatchAction(dict):
    @property
    def name(self):
        return self.get("name")

    @property
    def label(self):
        return self.get("label")

    @property
    def sprite(self):
        return self.get("sprite")

    @property
    def description(self):
        return self.get("description")

    @property
    def form_class(self):
        form_class = self.get("form_class")
        if isinstance(form_class, str):
            return import_string(form_class)
        return form_class


class BatchActionsBag(list[BatchAction]):
    @staticmethod
    def sort_by_position(action: BatchAction):
        p = action.get("position") or 0
        if p > 0:
            return (0, -p)  # positives, highest first
        if p == 0:
            return (1, 0)  # None/0, middle
        return (2, -p)  # negatives, closer to 0 first

    def __init__(self, seq=()):
        super().__init__(sorted(seq, key=BatchActionsBag.sort_by_position))

    def get_action(self, action_slug):
        for action in self:
            if action.name == action_slug:
                return action
        return None


# model_name (Model._meta.model_name) -> BatchActions subclass
BATCH_REGISTRY = {}


def register_batch_actions(cls):
    """Class decorator adding a BatchActions subclass to the registry."""
    BATCH_REGISTRY[cls.model._meta.model_name] = cls
    return cls


def get_batch_actions_class(model_name):
    return BATCH_REGISTRY.get(model_name)


class BatchActions:
    """
    Base class for per-model batch actions. Subclass, set ``model``, register
    with @register_batch_actions and add @batch_action methods taking
    ``(self, queryset, **form_data)``. Methods may return an extra message
    string appended to the success flash.
    """

    model = None
    # How the client refreshes after a successful action: "list" fires the
    # refreshItems HX-Trigger (dashboard re-runs the search in place),
    # "page" answers with HX-Refresh (plain list pages reload).
    post_action_refresh = "page"

    def __init__(self, user):
        self.user = user

    @classmethod
    def model_name(cls):
        return cls.model._meta.model_name

    def base_queryset(self):
        return self.model.objects.filter(user=self.user)

    def apply_query(self, queryset, q):
        """Filter the queryset by a search string (select_all selections).

        Models without a search language keep the default: select_all means
        every object of the user.
        """
        return queryset

    def resolve_selection(self, data):
        """
        Turn a request payload (QueryDict) into an owned queryset.

        ``select_all=1`` wins over explicit ``ids``; ownership is always
        enforced through base_queryset().
        """
        queryset = self.base_queryset()
        if data.get("select_all"):
            queryset = self.apply_query(queryset, (data.get("q") or "").strip())
            excluded = self._parse_ids(data, "excluded_ids")
            if excluded:
                queryset = queryset.exclude(pk__in=excluded)
            return queryset
        return queryset.filter(pk__in=self._parse_ids(data, "ids"))

    @staticmethod
    def _parse_ids(data, key):
        """Collect ints from repeated params and comma-separated values."""
        ids = []
        for raw in data.getlist(key):
            for part in str(raw).split(","):
                part = part.strip()
                if part.isdigit():
                    ids.append(int(part))
        return ids

    def get_available_actions(self) -> BatchActionsBag:
        actions = []
        for method_name in dir(self):
            if method_name.startswith("_"):
                continue
            method = getattr(self, method_name, None)
            meta = getattr(method, "_batch_action", None)
            if meta:
                actions.append(BatchAction(meta))
        return BatchActionsBag(actions)

    def get_action(self, action_slug) -> BatchAction:
        return self.get_available_actions().get_action(action_slug)

    def filter_applicable(self, action: BatchAction, queryset):
        """Restrict a selection to the objects the action may touch."""
        applicable = action.get("applicable")
        if applicable is None:
            return queryset
        return applicable(self, queryset)

    def run(self, action: BatchAction, queryset, **form_data):
        """
        Execute an action on the (already applicability-filtered) queryset.

        The selection is frozen to a pk list first: search-based selections
        can carry M2M joins (duplicated rows, no .update()) and the action
        itself may mutate the fields the query filters on.

        Returns (applied_count, extra_message_or_None).
        """
        ids = list(queryset.values_list("pk", flat=True).distinct())
        frozen = self.model.objects.filter(pk__in=ids)
        with transaction.atomic():
            extra = getattr(self, action.name)(frozen, **form_data)
        return len(ids), extra


@register_batch_actions
class ItemBatchActions(BatchActions):
    model = Item
    post_action_refresh = "list"

    def apply_query(self, queryset, q):
        from .search import apply_search

        return apply_search(queryset, q)

    @batch_action(
        label=_("Add tag"),
        sprite="lucide-plus",
        form_class="task_processor.forms.BatchAddTagForm",
        position=20,
    )
    def add_tag(self, queryset, tag):
        tag.item_set.add(*queryset)

    @batch_action(
        label=_("Remove tag"),
        sprite="lucide-minus",
        form_class="task_processor.forms.BatchRemoveTagForm",
        position=10,
    )
    def remove_tag(self, queryset, tag):
        tag.item_set.remove(*queryset)

    @batch_action(
        label=_("Replace area"),
        sprite="lucide-target",
        form_class="task_processor.forms.BatchAreaForm",
        description=_(
            "Sets the area on every selected item, overwriting any current area."
        ),
        position=5,
    )
    def replace_area(self, queryset, area):
        queryset.update(area=area)

    @batch_action(
        label=_("Add area"),
        sprite="lucide-target",
        form_class="task_processor.forms.BatchAreaForm",
        applicable=lambda actions, queryset: queryset.filter(area__isnull=True),
        description=_(
            "Sets the area on items that have none. Items already assigned "
            'to an area are skipped (use "Replace area" to overwrite).'
        ),
        position=4,
    )
    def add_area(self, queryset, area):
        """Set the area only on items that have none (see ``applicable``)."""
        queryset.update(area=area)

    @batch_action(label=_("Remove area"), sprite="lucide-circle-x", position=-10)
    def remove_area(self, queryset):
        queryset.update(area=None)


@register_batch_actions
class TagBatchActions(BatchActions):
    model = Tag

    @batch_action(
        label=_("Convert to area"),
        sprite="lucide-refresh-cw",
        form_class="task_processor.forms.BatchConvertToAreaForm",
        description=_(
            "Moves each tag's items into an area and removes the tag from "
            "them. Items already in a different area are left untouched and "
            "keep the tag."
        ),
    )
    def convert_to_area(self, queryset, area=None, delete_source=False):
        """
        Move each tag's items to an area and detach the tag from them.

        Destination: the picked ``area`` (merge) or, per tag, an area of the
        same name (created if missing). Items already in a *different* area
        are skipped and keep the tag — no silent overwrite, so converting
        overlapping tags is order-independent. ``delete_source`` removes a
        tag only once no items remain attached (mirror of the
        migrate_tag_to_area --delete-tag guard).
        """
        moved = skipped = 0
        kept = []
        for tag in queryset:
            destination = area
            if destination is None:
                destination, _created = Area.objects.get_or_create(
                    user=self.user,
                    name=tag.name[: Area._meta.get_field("name").max_length],
                    defaults={"description": f'Converted from tag "{tag.name}"'},
                )
            movable_ids = list(
                Item.objects.filter(user=self.user, tags=tag)
                .filter(Q(area__isnull=True) | Q(area=destination))
                .values_list("pk", flat=True)
            )
            Item.objects.filter(pk__in=movable_ids).update(area=destination)
            tag.item_set.remove(*movable_ids)
            moved += len(movable_ids)
            remaining = tag.item_set.count()
            skipped += remaining
            if remaining == 0 and delete_source:
                tag.delete()
            elif remaining and delete_source:
                kept.append(tag.name)
        parts = [f"{moved} item(s) moved"]
        if skipped:
            parts.append(f"{skipped} item(s) skipped (already in another area)")
        if kept:
            parts.append("tag(s) kept because of skipped items: " + ", ".join(kept))
        return ", ".join(parts)


@register_batch_actions
class AreaBatchActions(BatchActions):
    model = Area

    @batch_action(
        label=_("Convert to tag"),
        sprite="lucide-refresh-cw",
        form_class="task_processor.forms.BatchConvertToTagForm",
        description=_("Tags each area's items and clears their area assignment."),
    )
    def convert_to_tag(self, queryset, tag=None, delete_source=False):
        """
        Tag each area's items and clear their area. Never conflicts (tags are
        M2M): every item moves. Destination: the picked ``tag`` (merge) or,
        per area, a tag of the same name (created if missing).
        """
        moved = 0
        for area in queryset:
            destination = tag
            if destination is None:
                destination, _created = Tag.objects.get_or_create(
                    user=self.user,
                    name=area.name[: Tag._meta.get_field("name").max_length],
                )
            item_ids = list(
                Item.objects.filter(user=self.user, area=area).values_list(
                    "pk", flat=True
                )
            )
            destination.item_set.add(*item_ids)
            Item.objects.filter(pk__in=item_ids).update(area=None)
            moved += len(item_ids)
            if delete_source:
                area.delete()
        return f"{moved} item(s) moved"
