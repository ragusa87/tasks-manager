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
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from task_processor.constants import GTDConfig, GTDStatus
from task_processor.models import Item
from task_processor.models.base_models import Area, Context, Tag
from task_processor.models.item import ItemFlow


def batch_action(
    label,
    sprite=None,
    form_class=None,
    position=0,
    applicable=None,
    description=None,
    impact=None,
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
        impact: Optional ``callable(actions, queryset) -> str | None``
            returning a sentence about the action's downstream effect on
            *other* objects (e.g. how many items a tag conversion will move),
            computed on the applicable selection and shown in the confirm
            modal preview.
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
            "impact": impact,
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
    string appended to the success flash, or an ``(applied_count, extra)``
    tuple when the action can skip part of the queryset itself (so the flash
    reports what actually changed, not the selection size).
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

    def describe_impact(self, action: BatchAction, queryset):
        """Sentence about the action's effect on other objects, or None."""
        impact = action.get("impact")
        if impact is None:
            return None
        return impact(self, queryset)

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
            result = getattr(self, action.name)(frozen, **form_data)
        if isinstance(result, tuple):
            return result
        return len(ids), result


def formless_transition_groups():
    """
    The ItemFlow transitions offered by the batch "Move" action, grouped by
    label — methods sharing a label are alternatives (inbox→next and
    someday→next are both "Next Action"); per item, the one its state allows
    runs. Excludes @requires_form transitions and @batchable(enabled=False).

    Returns an ordered dict keyed by the group's first method name (stable
    across locales, unlike the translated label):
    ``{key: {"label", "methods", "target", "q"}}`` where ``q`` is the SQL
    equivalent of "some method of this group can proceed": status ∈ source
    states (no constraint for State.ANY), AND'ed per method with its
    @batchable ``filter_q``. Query filters, not per-item ``can_proceed()``:
    select-all previews must count in the database, not load every row.

    Deliberately not cached (pure introspection, microseconds): a cache would
    freeze the ``filter_q`` results — promised deferred so they may depend on
    the current time — and the labels' translation in the first request's
    locale.
    """
    flow = ItemFlow(Item())
    statuses = set(GTDStatus.values)
    methods = {}
    for entry in flow.get_all_transitions():
        if entry.form_class:
            continue
        meta = flow._get_annotated_property(entry.name, "_batchable") or {}
        if meta.get("enabled") is False:
            continue
        method = methods.setdefault(
            entry.name,
            {
                "sources": [],
                "label": str(entry.label),
                "target": entry.get("target"),
                "filter_q": meta.get("filter_q"),
            },
        )
        method["sources"].append(entry.get("source"))
    by_label = {}
    for name, info in methods.items():
        sources = [s for s in info["sources"] if s in statuses]
        # A source outside the status values is fsm.State.ANY: no constraint.
        q = Q(status__in=sources) if len(sources) == len(info["sources"]) else Q()
        if info["filter_q"]:
            q &= info["filter_q"]()
        group = by_label.get(info["label"])
        if group is None:
            by_label[info["label"]] = {
                "label": info["label"],
                "methods": [name],
                "target": info["target"],
                "q": q,
            }
        else:
            group["methods"].append(name)
            group["q"] = group["q"] | q
    return {group["methods"][0]: group for group in by_label.values()}


def _childless(queryset):
    """Items with no sub-items of their own.

    Subquery over the parent FK (mirroring the ``has:children`` search filter)
    rather than ``sub_items__isnull=True``, whose reverse join would drop or
    duplicate rows. Pks are globally unique, so no user scoping is needed.
    """
    return queryset.exclude(
        pk__in=Item.objects.filter(parent__isnull=False).values("parent")
    )


def _merge_applicable(actions, queryset):
    """Top-level projects/references, and only when there are at least two:
    merging fewer is meaningless, so the preview shows 'not applicable' and
    the confirm button stays hidden."""
    applicable = queryset.filter(
        parent__isnull=True, status__in=GTDConfig.STATUS_WITH_PARENT_ALLOWED
    )
    if applicable.order_by().values("pk").distinct().count() < 2:
        return applicable.none()
    return applicable


def _merge_impact(actions, queryset):
    """Children moved by the merge, counted in one aggregate query."""
    count = Item.objects.filter(user=actions.user, parent__in=queryset).count()
    if not count:
        return _("The selected items have no children: merging will change nothing.")
    return _(
        "%(count)d child item(s) will be moved under the item you pick; "
        "the other selected items are kept, emptied."
    ) % {"count": count}


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
        tag.item_set.add(*queryset.values_list("pk", flat=True))

    @batch_action(
        label=_("Remove tag"),
        sprite="lucide-minus",
        form_class="task_processor.forms.BatchRemoveTagForm",
        position=10,
    )
    def remove_tag(self, queryset, tag):
        tag.item_set.remove(*queryset.values_list("pk", flat=True))

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

    @batch_action(
        label=_("Move"),
        sprite="lucide-replace-all",
        form_class="task_processor.forms.BatchTransitionForm",
        description=_(
            "Applies a status transition to every selected item whose "
            "current state allows it."
        ),
        position=2,
    )
    def move(self, queryset, transition):
        """Apply the chosen form-less transition group to the selection.

        SQL pre-filter loads only the rows the group's states allow; the
        per-item can_proceed() guard stays authoritative (it also covers
        python conditions lacking a @batchable filter_q). Execution goes
        through item.flow so FSM on_success saves and post_save signals
        (reminder/rrule clearing) behave exactly like single transitions.

        ``transition`` may also be the "delete" pseudo-transition offered by
        BatchTransitionForm: not part of the flow, but every item is deletable
        (mirroring ItemDeleteView). Like the single-item delete it cascades to
        children (parent FK) and documents, whose stored files are cleaned up
        by the Document post_delete receiver.
        """
        if transition == "delete":
            deleted = queryset.delete()[1].get(Item._meta.label, 0)
            return deleted, gettext("deleted")
        group = formless_transition_groups()[transition]
        total = queryset.count()
        applied = 0
        for item in queryset.filter(group["q"]):
            flow = item.flow
            method = next(
                (
                    getattr(flow, name)
                    for name in group["methods"]
                    if getattr(flow, name).can_proceed()
                ),
                None,
            )
            if method:
                method()
                applied += 1
        skipped = total - applied
        extra = gettext("moved to %(label)s") % {"label": group["label"]}
        if skipped:
            extra += gettext(", %(skipped)d skipped (state does not allow it)") % {
                "skipped": skipped
            }
        return applied, extra

    # Sources of the two @requires_form reference transitions
    # (process_as_reference: inbox, convert_as_reference: next_action).
    # "Move" only offers form-less transitions, so the reference conversion
    # gets its own action carrying the optional-parent form.
    REFERENCE_SOURCES = (GTDStatus.INBOX, GTDStatus.NEXT_ACTION)

    @batch_action(
        label=_("Convert to reference"),
        sprite="lucide-book-marked",
        form_class="task_processor.forms.BatchReferenceForm",
        applicable=lambda actions, queryset: queryset.filter(
            status__in=actions.REFERENCE_SOURCES
        ),
        description=_(
            "Turns each selected inbox or next-action item into reference "
            "material, optionally filed under a project or reference. Items "
            "in other states are skipped."
        ),
        position=1,
    )
    def convert_to_reference(self, queryset, parent=None):
        """Run the status-specific reference transition per item.

        Execution goes through item.flow (like "Move") so FSM guards and
        signals behave exactly like single-item conversions.

        When no parent is chosen in the form (``parent is None``), each item
        keeps its current parent instead of being moved to the top level: the
        reference transitions overwrite ``item.parent`` unconditionally, so we
        pass the item's existing parent back in.
        """
        applied = 0
        for item in queryset:
            flow = item.flow
            method = next(
                (
                    getattr(flow, name)
                    for name in ("process_as_reference", "convert_as_reference")
                    if getattr(flow, name).can_proceed()
                ),
                None,
            )
            if method:
                method(parent=parent if parent is not None else item.parent)
                applied += 1
        return applied, None

    @batch_action(
        label=_("Move under…"),
        sprite="lucide-folder-tree",
        form_class="task_processor.forms.BatchMoveUnderForm",
        applicable=lambda actions, queryset: _childless(queryset),
        description=_(
            "Re-parents each selected item under the project or reference you "
            "pick. Items that have their own sub-items are skipped: nesting "
            "them would exceed the maximum project depth."
        ),
        position=3,
    )
    def move_under(self, queryset, parent):
        """Re-parent childless items under a top-level project/reference.

        A plain .update(): no status change, and a childless item moved under
        a top-level target lands at depth 1 — always within MAX_DEPTH and never
        circular (it has no descendants the target could belong to). The target
        is excluded so a selected item chosen as its own destination is a
        no-op rather than a self-parent.
        """
        moved = queryset.exclude(pk=parent.pk).update(parent=parent)
        return moved, None

    @batch_action(
        label=_("Merge"),
        sprite="lucide-merge",
        form_class="task_processor.forms.BatchMergeTopLevelForm",
        applicable=_merge_applicable,
        description=_(
            "Moves every child of the selected top-level projects and "
            "references under the one you pick; the others are kept as "
            "empty top-level items. Applies only when at least two selected "
            "items are top-level projects or references."
        ),
        impact=_merge_impact,
        position=0,
    )
    def merge_top_level(self, queryset, target):
        """Re-parent all direct children of the non-target selected items.

        A plain .update(): no status change (so no FSM transition), and
        nothing listens to parent changes. Grandchildren follow automatically
        (only the direct parent FK moves) and MAX_DEPTH is preserved: sources
        and target are all top-level, so every moved subtree keeps its depth.
        """
        sources = queryset.exclude(pk=target.pk)
        moved = Item.objects.filter(user=self.user, parent__in=sources).update(
            parent=target
        )
        return gettext('%(moved)d child item(s) moved under "%(title)s"') % {
            "moved": moved,
            "title": target.title,
        }


# --- Conversion helpers -----------------------------------------------------
# Tag and Context are both plain M2M labels on Item, so their conversions
# share the same mechanics; ``field_name`` is the Item M2M field ("tags" /
# "contexts") and ``noun`` the translated label kind for messages.


def _items_carrying(actions, field_name, queryset):
    return Item.objects.filter(
        user=actions.user, **{f"{field_name}__in": queryset}
    ).distinct()


def _m2m_to_area_impact(field_name, noun):
    """Impact preview for M2M→area conversions (tag→area, context→area).

    Computed before the destination is chosen, so items that already have an
    area are reported as "skipped unless it matches the destination".
    """

    def impact(actions, queryset):
        items = _items_carrying(actions, field_name, queryset)
        total = items.count()
        if not total:
            return _("No items carry the selected %(noun)s.") % {"noun": noun}
        blocked = items.exclude(area__isnull=True).count()
        if blocked:
            return _(
                "%(total)d item(s) carry the selected %(noun)s: %(movable)d "
                "will be moved, %(blocked)d already have an area and will be "
                "skipped unless it matches the destination."
            ) % {
                "total": total,
                "noun": noun,
                "movable": total - blocked,
                "blocked": blocked,
            }
        return _("%(total)d item(s) carry the selected %(noun)s and will be moved.") % {
            "total": total,
            "noun": noun,
        }

    return impact


def _m2m_to_m2m_impact(field_name, noun, dest_noun):
    """Impact preview for M2M→M2M conversions (always exact, no conflicts)."""

    def impact(actions, queryset):
        count = _items_carrying(actions, field_name, queryset).count()
        if not count:
            return _("No items carry the selected %(noun)s.") % {"noun": noun}
        return _(
            "%(count)d item(s) will get the %(dest_noun)s and lose the %(noun)s."
        ) % {"count": count, "noun": noun, "dest_noun": dest_noun}

    return impact


def _convert_to_tag_impact(actions, queryset):
    """Item count for the area→tag confirm preview (always exact)."""
    count = Item.objects.filter(user=actions.user, area__in=queryset).count()
    if not count:
        return _("No items are assigned to the selected area(s).")
    return _("%(count)d item(s) will be tagged and their area cleared.") % {
        "count": count
    }


def _convert_m2m_sources_to_area(
    actions, queryset, field_name, noun, area=None, delete_source=False
):
    """
    Move each source label's items to an area and detach the label from them.

    Destination: the picked ``area`` (merge) or, per source, an area of the
    same name (created if missing). Items already in a *different* area are
    skipped and keep the label — no silent overwrite, so converting
    overlapping labels is order-independent. ``delete_source`` removes a
    source only once no items remain attached.
    """
    moved = skipped = 0
    kept = []
    for source in queryset:
        destination = area
        if destination is None:
            destination, _created = Area.objects.get_or_create(
                user=actions.user,
                name=source.name[: Area._meta.get_field("name").max_length],
                defaults={
                    "description": gettext('Converted from %(noun)s "%(name)s"')
                    % {"noun": noun, "name": source.name}
                },
            )
        movable_ids = list(
            Item.objects.filter(user=actions.user, **{field_name: source})
            .filter(Q(area__isnull=True) | Q(area=destination))
            .values_list("pk", flat=True)
        )
        Item.objects.filter(pk__in=movable_ids).update(area=destination)
        source.item_set.remove(*movable_ids)
        moved += len(movable_ids)
        remaining = source.item_set.count()
        skipped += remaining
        if remaining == 0 and delete_source:
            source.delete()
        elif remaining and delete_source:
            kept.append(source.name)
    parts = [gettext("%(moved)d item(s) moved") % {"moved": moved}]
    if skipped:
        parts.append(
            gettext("%(skipped)d item(s) skipped (already in another area)")
            % {"skipped": skipped}
        )
    if kept:
        parts.append(
            gettext("%(noun)s(s) kept because of skipped items: %(names)s")
            % {"noun": noun, "names": ", ".join(kept)}
        )
    return ", ".join(parts)


def _convert_m2m_sources_to_m2m(
    actions, queryset, field_name, dest_model, destination=None, delete_source=False
):
    """
    Re-label each source's items with a label of another M2M kind (tag→context,
    context→tag). Never conflicts: every item moves. Destination: the picked
    one (merge) or, per source, a same-name label (created if missing).
    """
    moved = 0
    for source in queryset:
        dest = destination
        if dest is None:
            dest, _created = dest_model.objects.get_or_create(
                user=actions.user,
                name=source.name[: dest_model._meta.get_field("name").max_length],
            )
        item_ids = list(
            Item.objects.filter(user=actions.user, **{field_name: source}).values_list(
                "pk", flat=True
            )
        )
        dest.item_set.add(*item_ids)
        source.item_set.remove(*item_ids)
        moved += len(item_ids)
        if delete_source:
            source.delete()
    return gettext("%(moved)d item(s) moved") % {"moved": moved}


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
        impact=_m2m_to_area_impact("tags", _("tag(s)")),
    )
    def convert_to_area(self, queryset, area=None, delete_source=False):
        return _convert_m2m_sources_to_area(
            self, queryset, "tags", _("tag"), area=area, delete_source=delete_source
        )

    @batch_action(
        label=_("Convert to context"),
        sprite="lucide-refresh-cw",
        form_class="task_processor.forms.BatchConvertToContextForm",
        description=_(
            "Adds a context to each tag's items and removes the tag from them."
        ),
        impact=_m2m_to_m2m_impact("tags", _("tag(s)"), _("context")),
        position=-5,
    )
    def convert_to_context(self, queryset, context=None, delete_source=False):
        return _convert_m2m_sources_to_m2m(
            self,
            queryset,
            "tags",
            Context,
            destination=context,
            delete_source=delete_source,
        )


@register_batch_actions
class ContextBatchActions(BatchActions):
    model = Context

    @batch_action(
        label=_("Convert to tag"),
        sprite="lucide-refresh-cw",
        form_class="task_processor.forms.BatchContextToTagForm",
        description=_("Tags each context's items and removes the context from them."),
        impact=_m2m_to_m2m_impact("contexts", _("context(s)"), _("tag")),
    )
    def convert_to_tag(self, queryset, tag=None, delete_source=False):
        return _convert_m2m_sources_to_m2m(
            self,
            queryset,
            "contexts",
            Tag,
            destination=tag,
            delete_source=delete_source,
        )

    @batch_action(
        label=_("Convert to area"),
        sprite="lucide-refresh-cw",
        form_class="task_processor.forms.BatchContextToAreaForm",
        description=_(
            "Moves each context's items into an area and removes the context "
            "from them. Items already in a different area are left untouched "
            "and keep the context."
        ),
        impact=_m2m_to_area_impact("contexts", _("context(s)")),
        position=-5,
    )
    def convert_to_area(self, queryset, area=None, delete_source=False):
        return _convert_m2m_sources_to_area(
            self,
            queryset,
            "contexts",
            _("context"),
            area=area,
            delete_source=delete_source,
        )


@register_batch_actions
class AreaBatchActions(BatchActions):
    model = Area

    @batch_action(
        label=_("Convert to tag"),
        sprite="lucide-refresh-cw",
        form_class="task_processor.forms.BatchConvertToTagForm",
        description=_("Tags each area's items and clears their area assignment."),
        impact=_convert_to_tag_impact,
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
        return gettext("%(moved)d item(s) moved") % {"moved": moved}
