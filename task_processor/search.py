import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, NamedTuple

from django.db.models import Q, TextChoices

from task_processor.constants import GTDEnergy


class FilterCategory(TextChoices):
    STATUS = "status", "Status"
    PRIORITY = "priority", "Priority"
    DUE = "due", "Due Date"
    ENERGY = "energy", "Energy"
    RELATIONSHIP = "relationship", "Relationship"
    AREA = "area", "Area"
    CONTEXT = "context", "Context"
    PROJECT = "project", "Project"


class FilterStrategy(Enum):
    """
    Defines how filters behave when toggled in the search interface.

    NORMAL: Additive strategy - filters can be combined.
            Toggling: inactive -> active -> inactive
            Example: has:project, has:context can both be active

    EXCLUSIVE: Mutually exclusive - only one filter of the same field can be active.
               Toggling: inactive -> active (replaces others) -> inactive
               Example: priority:high replaces priority:low

    INVERT: Three-state cycle with negation support.
            Toggling: inactive -> active (included) -> inverted (excluded) -> inactive
            Example: area:Work -> -area:Work -> removed

    REPLACE: Replaces ALL filters (not just same field).
             Toggling: inactive -> active (clears all) -> inverted -> inactive
             Example: in:inbox clears priority:high, has:project, etc.
    """

    NORMAL = "normal"
    EXCLUSIVE = "exclusive"
    INVERT = "invert"
    REPLACE = "replace"


FILTER_STRATEGY_MAP = {
    FilterCategory.STATUS: FilterStrategy.REPLACE,
    FilterCategory.PRIORITY: FilterStrategy.EXCLUSIVE,
    FilterCategory.DUE: FilterStrategy.EXCLUSIVE,
    FilterCategory.ENERGY: FilterStrategy.EXCLUSIVE,
    FilterCategory.RELATIONSHIP: FilterStrategy.NORMAL,
    FilterCategory.AREA: FilterStrategy.INVERT,
    FilterCategory.CONTEXT: FilterStrategy.NORMAL,
    FilterCategory.PROJECT: FilterStrategy.EXCLUSIVE,
}


@dataclass
class SearchTokens:
    original_query: str
    included: Dict[str, List[str]] = field(default_factory=dict)
    excluded: Dict[str, List[str]] = field(default_factory=dict)
    query: str = ""


class FilterOption(NamedTuple):
    """Represents a single filter option in the search interface."""

    label: str
    filter_query: str
    icon: str
    color: str
    category: FilterCategory
    active: bool = False
    inversed: bool = False  # True if this filter is excluded (negated)
    next_query: str = ""  # The query that would result from clicking this filter

    @property
    def inactive_classes(self) -> str:
        """More vibrant inactive state with better contrast and subtle gradients"""
        return f"filter-suggestion filter-{self.color} filter-suggestion-inactive"

    @property
    def active_classes(self) -> str:
        """Bold, vibrant active state with strong visual feedback"""
        return f"filter-suggestion filter-{self.color} filter-suggestion-active"

    @property
    def inversed_classes(self) -> str:
        """CSS classes for inversed (excluded) state."""
        return f"filter-suggestion filter-{self.color} filter-suggestion-active filter-suggestion-inversed"

    @property
    def current_classes(self) -> str:
        """CSS classes for current state (active/inactive/inversed)."""
        if self.active:
            if self.inversed:
                return self.inversed_classes
            else:
                return self.active_classes
        else:
            return self.inactive_classes


class SearchFilter:
    """
    Generates filter options for the search interface based on user's data.

    This class provides structured filter options that can be used in templates
    to generate dynamic search suggestions and filters.
    """

    def __init__(self, user=None, areas=None, contexts=None, projects=None):
        self.user = user
        self.areas = areas or []
        self.contexts = contexts or []
        self.projects = projects or []

    def get_all_filters(self) -> List[FilterOption]:
        """Get all filter options."""
        filters = []

        # Status filters (exclusive)
        filters.extend(
            [
                FilterOption(
                    "Inbox", "in:inbox", "lucide-inbox", "blue", FilterCategory.STATUS
                ),
                FilterOption(
                    "Next Actions",
                    "in:next",
                    "lucide-zap",
                    "blue",
                    FilterCategory.STATUS,
                ),
                FilterOption(
                    "Waiting For",
                    "in:waiting",
                    "lucide-hourglass",
                    "blue",
                    FilterCategory.STATUS,
                ),
                FilterOption(
                    "Someday",
                    "in:someday",
                    "lucide-history",
                    "blue",
                    FilterCategory.STATUS,
                ),
                FilterOption(
                    "Projects",
                    "in:project",
                    "lucide-briefcase",
                    "blue",
                    FilterCategory.STATUS,
                ),
                FilterOption(
                    "Reference",
                    "in:reference",
                    "lucide-archive",
                    "blue",
                    FilterCategory.STATUS,
                ),
                FilterOption(
                    "Cancelled",
                    "in:cancelled",
                    "lucide-trash-2",
                    "blue",
                    FilterCategory.STATUS,
                ),
            ]
        )

        # Priority filters
        filters.extend(
            [
                FilterOption(
                    "Low Priority",
                    "priority:low",
                    "lucide-arrow-down",
                    "red",
                    FilterCategory.PRIORITY,
                ),
                FilterOption(
                    "Normal Priority",
                    "priority:normal",
                    "lucide-minus",
                    "red",
                    FilterCategory.PRIORITY,
                ),
                FilterOption(
                    "High Priority",
                    "priority:high",
                    "lucide-arrow-up",
                    "red",
                    FilterCategory.PRIORITY,
                ),
                FilterOption(
                    "Urgent Priority",
                    "priority:urgent",
                    "lucide-circle-alert",
                    "red",
                    FilterCategory.PRIORITY,
                ),
            ]
        )

        # Due date filters
        filters.extend(
            [
                FilterOption(
                    "Has Due Date",
                    "has:due",
                    "lucide-calendar-clock",
                    "orange",
                    FilterCategory.DUE,
                ),
                FilterOption(
                    "Overdue",
                    "is:overdue",
                    "lucide-triangle-alert",
                    "orange",
                    FilterCategory.DUE,
                ),
                FilterOption(
                    "Due Today",
                    "is:due",
                    "lucide-calendar",
                    "orange",
                    FilterCategory.DUE,
                ),
                FilterOption(
                    "Due Soon", "is:soon", "lucide-clock", "orange", FilterCategory.DUE
                ),
            ]
        )

        # Energy filters
        filters.extend(
            [
                FilterOption(
                    "Low Energy",
                    "energy:low",
                    "lucide-battery-low",
                    "yellow",
                    FilterCategory.ENERGY,
                ),
                FilterOption(
                    "Normal Energy",
                    "energy:normal",
                    "lucide-battery",
                    "yellow",
                    FilterCategory.ENERGY,
                ),
                FilterOption(
                    "Medium Energy",
                    "energy:medium",
                    "lucide-battery-medium",
                    "yellow",
                    FilterCategory.ENERGY,
                ),
                FilterOption(
                    "High Energy",
                    "energy:high",
                    "lucide-battery-full",
                    "yellow",
                    FilterCategory.ENERGY,
                ),
            ]
        )

        # Relationship filters
        filters.extend(
            [
                FilterOption(
                    "Has Project",
                    "has:project",
                    "lucide-folder",
                    "blue",
                    FilterCategory.RELATIONSHIP,
                ),
                FilterOption(
                    "Has Context",
                    "has:context",
                    "lucide-hash",
                    "blue",
                    FilterCategory.RELATIONSHIP,
                ),
                FilterOption(
                    "Has Area",
                    "has:area",
                    "lucide-target",
                    "blue",
                    FilterCategory.RELATIONSHIP,
                ),
                FilterOption(
                    "Has Description",
                    "has:description",
                    "lucide-file-text",
                    "blue",
                    FilterCategory.RELATIONSHIP,
                ),
            ]
        )

        # Area filters
        filters.extend(
            [
                FilterOption(
                    area.name,
                    f'area:"{area.name}"',
                    "lucide-at-sign",
                    "green",
                    FilterCategory.AREA,
                )
                for area in self.areas
            ]
        )

        # Context filters
        filters.extend(
            [
                FilterOption(
                    context.name,
                    f'context:"{context.name}"',
                    "lucide-hash",
                    "purple",
                    FilterCategory.CONTEXT,
                )
                for context in self.contexts
            ]
        )

        # Projects filters
        filters.extend(
            [
                FilterOption(
                    project.title,
                    f"project:{project.pk}",
                    "lucide-briefcase",
                    "purple",
                    FilterCategory.PROJECT,
                )
                for project in self.projects
            ]
        )

        return filters

    def get_filters_by_category(
        self, category: FilterCategory = None
    ) -> List[FilterOption]:
        """Get filter options filtered by category."""
        all_filters = self.get_all_filters()
        if category:
            return [f for f in all_filters if f.category == category]
        return all_filters

    def get_popular_filters(self) -> List[FilterOption]:
        """Get commonly used filter options for quick access."""
        return [
            FilterOption(
                "Inbox", "in:inbox", "lucide-inbox", "blue", FilterCategory.STATUS
            ),
            FilterOption(
                "Next Actions", "in:next", "lucide-zap", "blue", FilterCategory.STATUS
            ),
            FilterOption(
                "Overdue",
                "is:overdue",
                "lucide-triangle-alert",
                "orange",
                FilterCategory.DUE,
            ),
            FilterOption(
                "Due Today", "is:due", "lucide-calendar", "orange", FilterCategory.DUE
            ),
            FilterOption(
                "High Priority",
                "priority:high",
                "lucide-arrow-up",
                "red",
                FilterCategory.PRIORITY,
            ),
            FilterOption(
                "Has Project",
                "has:project",
                "lucide-folder",
                "blue",
                FilterCategory.RELATIONSHIP,
            ),
        ]

    def get_filters_with_state(
        self, search_query: str
    ) -> Dict[str, List[FilterOption]]:
        """Get all filter options with active/inversed state based on current search query."""
        # Parse the search query to get tokens
        parser = SearchParser()
        tokens = parser.parse(search_query)

        # Organize by category
        filters_by_category = {}

        # Group filters by category
        for category in FilterCategory:
            category_filters = self.get_filters_by_category(category)
            if category_filters:
                filters_by_category[category.value] = parser.apply_tokens_to_filters(
                    tokens, category_filters, search_query
                )

        return filters_by_category


class SearchParser:
    """
    Parser for advanced search queries with field-specific filters.

    Supports:
    - Field filters: in:inbox, tags:"value", priority:high
    - Exclusions: -in:inbox, -tags:"value", -priority:high
    - Quoted values: tags:"my tag", "exact phrase"
    - Free text search: remaining words become general query

    Example: 'in:inbox tags:"train","my god" is:overdue priority:-low coucou'
    """

    # Regex patterns for parsing
    FIELD_PATTERN = re.compile(r'(-?)(\w+):((?:"[^"]*"(?:,"[^"]*")*)|(?:[^\s]+))')
    QUOTED_STRING_PATTERN = re.compile(r'"([^"]*)"')

    def __init__(self, **kwargs):
        self.forced_query = kwargs.get("forced_query", "")
        pass

    def parse(self, query_string: str) -> SearchTokens:
        """Parse a search query string into structured tokens."""
        if not query_string:
            return SearchTokens(original_query="")

        tokens = SearchTokens(original_query=query_string.strip())
        remaining_query = query_string.strip()

        # Find all field:value patterns
        for match in self.FIELD_PATTERN.finditer(query_string):
            is_excluded = bool(match.group(1))  # Starts with '-'
            field_name = match.group(2)
            field_value = match.group(3)

            # Parse the field value (handle quoted strings and comma-separated values)
            values = self._parse_field_value(field_value)

            # Add to appropriate collection
            target = tokens.excluded if is_excluded else tokens.included
            if field_name not in target:
                target[field_name] = []
            target[field_name].extend(values)

            # Remove this match from the remaining query
            remaining_query = remaining_query.replace(match.group(0), " ", 1)

        # Clean up remaining query (remove extra spaces, quotes)
        tokens.query = self._clean_remaining_query(remaining_query)

        return tokens

    def _parse_field_value(self, value_string: str) -> List[str]:
        """Parse field values, handling quoted strings and comma separation."""
        values = []

        if value_string.startswith('"') and value_string.endswith('"'):
            # Handle quoted comma-separated values: "value1","value2","value3"
            quoted_matches = self.QUOTED_STRING_PATTERN.findall(value_string)
            values.extend(quoted_matches)
        elif '"' in value_string:
            # Handle mixed quoted values
            quoted_matches = self.QUOTED_STRING_PATTERN.findall(value_string)
            values.extend(quoted_matches)
        else:
            # Handle unquoted single value or comma-separated values
            if "," in value_string:
                values.extend([v.strip() for v in value_string.split(",") if v.strip()])
            else:
                values.append(value_string)

        return values

    def _clean_remaining_query(self, remaining: str) -> str:
        """Clean up the remaining query string."""
        # Remove extra whitespace
        cleaned = re.sub(r"\s+", " ", remaining).strip()

        # Remove standalone quotes that might be left over
        cleaned = re.sub(r'(?:^|\s)"(?:\s|$)', " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        return (cleaned + " " + self.forced_query).strip()

    def apply_tokens_to_filters(
        self, tokens: SearchTokens, filters: List[FilterOption], current_query: str = ""
    ) -> List[FilterOption]:
        """Apply search tokens to filter options to set their active/inversed state and calculate future queries."""
        updated_filters = []

        for filter_option in filters:
            # Check if this filter's query matches any included or excluded tokens
            active = False
            inversed = False

            # Parse the filter query to check for matches
            filter_parts = self._parse_filter_query(filter_option.filter_query)

            for _field_name, value in filter_parts:
                # Check included tokens
                if _field_name in tokens.included:
                    for token_value in tokens.included[_field_name]:
                        if self._matches_filter_value(token_value, value):
                            active = True
                            inversed = False
                            break

                # Check excluded tokens
                if _field_name in tokens.excluded:
                    for token_value in tokens.excluded[_field_name]:
                        if self._matches_filter_value(token_value, value):
                            active = True
                            inversed = True
                            break

                if active:
                    break

            # Generate future query for this filter
            next_query = self.generate_future_query(
                current_query, filter_option, {"active": active, "inversed": inversed}
            )

            # Create new FilterOption with updated state and future query
            updated_filters.append(
                FilterOption(
                    label=filter_option.label,
                    filter_query=filter_option.filter_query,
                    icon=filter_option.icon,
                    color=filter_option.color,
                    category=filter_option.category,
                    active=active,
                    inversed=inversed,
                    next_query=next_query,
                )
            )

        return updated_filters

    def _parse_filter_query(self, query: str) -> List[tuple]:
        """Parse a filter query into field:value pairs."""
        parts = []
        # Handle simple field:value patterns
        matches = self.FIELD_PATTERN.findall(query)
        for match in matches:
            field_name = match[1]  # group 2 is field name
            field_value = match[2]  # group 3 is field value
            # Clean quotes from value
            clean_value = field_value.strip('"').lower()
            parts.append((field_name, clean_value))

        return parts

    def _normalize_value(self, value: str) -> str:
        """Normalize a value for consistent comparison and storage."""
        return value.strip("\"'").strip()

    def _needs_quoting(self, value: str) -> bool:
        """Determine if a value needs to be quoted in the query."""
        # Quote if contains spaces, special characters, or starts with @#!
        return (
            " " in value
            or any(char in value for char in "@#!,:")
            or value != value.strip()
        )

    def _format_value_for_query(self, value: str) -> str:
        """Format a value for inclusion in query string."""
        normalized = self._normalize_value(value)
        if self._needs_quoting(normalized):
            return f'"{normalized}"'
        return normalized

    def _extract_quoted_values(self, field_value: str) -> List[str]:
        """Extract values from field, handling mixed quoted/unquoted."""
        if "," in field_value:
            # Handle comma-separated values
            parts = []
            current = ""
            in_quotes = False

            for char in field_value:
                if char == '"' and (not current or current[-1] != "\\"):
                    in_quotes = not in_quotes
                    current += char
                elif char == "," and not in_quotes:
                    if current.strip():
                        parts.append(current.strip())
                    current = ""
                else:
                    current += char

            if current.strip():
                parts.append(current.strip())

            return [self._normalize_value(part) for part in parts]

        return [self._normalize_value(field_value)]

    def _format_grouped_values(self, values: List[str]) -> str:
        """Format multiple values for a field with proper quoting."""
        formatted_values = [self._format_value_for_query(value) for value in values]
        return ",".join(formatted_values)

    def _matches_filter_value(self, search_value: str, filter_value: str) -> bool:
        """Compare values ignoring quote differences."""
        return self._normalize_value(search_value) == self._normalize_value(
            filter_value
        )

    def _group_filters_by_field(
        self, tokens: SearchTokens
    ) -> Dict[str, Dict[str, List[str]]]:
        """Group included and excluded filters by field for concatenation."""
        grouped = {"included": {}, "excluded": {}}

        # Group included filters
        for _field, values in tokens.included.items():
            grouped["included"][_field] = values

        # Group excluded filters
        for _field, values in tokens.excluded.items():
            grouped["excluded"][_field] = values

        return grouped

    def _rebuild_query_string(self, tokens: SearchTokens, free_text: str = "") -> str:
        """Rebuild query string with proper quoting and grouping."""
        parts = []

        # Process included filters
        for _field, values in tokens.included.items():
            if values:
                formatted_values = self._format_grouped_values(values)
                parts.append(f"{_field}:{formatted_values}")

        # Process excluded filters
        for _field, values in tokens.excluded.items():
            if values:
                formatted_values = self._format_grouped_values(values)
                parts.append(f"-{_field}:{formatted_values}")

        # Add free text first if present
        if free_text.strip():
            parts.append(free_text.strip())

        return " ".join(parts)

    def generate_future_query(
        self,
        current_query: str,
        target_filter: FilterOption,
        current_state: Dict,
        strategy: FilterStrategy = None,
    ) -> str:
        """
        Generate the query that would result from toggling a specific filter.

        Args:
            current_query: The current search query string
            target_filter: The FilterOption being toggled
            current_state: {"active": bool, "inversed": bool}
            strategy: Optional FilterStrategy to use. If None, uses FILTER_STRATEGY_MAP based on category.

        Returns:
            The modified query string with the filter toggled
        """
        # Parse current query
        tokens = self.parse(current_query)

        # Parse target filter to get field and value
        filter_parts = self._parse_filter_query(target_filter.filter_query)
        if not filter_parts:
            return current_query  # Invalid filter, return unchanged

        field, value = filter_parts[0]
        is_active = current_state.get("active", False)
        is_inversed = current_state.get("inversed", False)

        # Determine strategy: use provided strategy or look up from category
        if strategy is None:
            strategy = FILTER_STRATEGY_MAP.get(
                target_filter.category, FilterStrategy.NORMAL
            )

        if strategy == FilterStrategy.EXCLUSIVE:
            self._apply_exclusive_filter_strategy(tokens, field, value, is_active)
        elif strategy == FilterStrategy.INVERT:
            self._apply_invert_filter_strategy(
                tokens, field, value, is_active, is_inversed
            )
        elif strategy == FilterStrategy.REPLACE:
            if is_inversed:
                tokens.included = {}
                tokens.excluded = {field: [value]}
            else:
                tokens.included = {field: [value]}
                tokens.excluded = {}
            self._apply_invert_filter_strategy(
                tokens, field, value, is_active, is_inversed
            )
        else:
            self._apply_normal_filter_strategy(
                tokens, field, value, is_active, is_inversed
            )

        # Rebuild query string
        return self._rebuild_query_string(tokens, tokens.query)

    def _apply_exclusive_filter_strategy(
        self, tokens: SearchTokens, field: str, value: str, is_active: bool
    ):
        """Apply exclusive filter strategy (replace -> remove)."""
        if is_active:
            # Remove the active filter completely
            self._remove_filter_value(tokens, field, value)
        else:
            # Replace all existing filters of this field with the new one
            if field in tokens.included:
                del tokens.included[field]
            if field in tokens.excluded:
                del tokens.excluded[field]
            # Add the new filter
            self._add_filter_value(tokens.included, field, value)

    def _apply_normal_filter_strategy(
        self,
        tokens: SearchTokens,
        field: str,
        value: str,
        is_active: bool,
        is_inversed: bool,
    ):
        """Apply normal filter strategy (add -> remove)."""
        if is_active:
            # Remove the filter (from included or excluded)
            self._remove_filter_value(tokens, field, value)
        else:
            # Add the filter to included
            self._add_filter_value(tokens.included, field, value)

    def _apply_invert_filter_strategy(
        self,
        tokens: SearchTokens,
        field: str,
        value: str,
        is_active: bool,
        is_inversed: bool,
    ):
        """Apply invert filter strategy (add -> invert -> remove cycle)."""
        if not is_active:
            # Case 1: Not active -> Add the filter to included
            self._add_filter_value(tokens.included, field, value)
        elif is_active and not is_inversed:
            # Case 2: Active and not inverted -> Invert it (move to excluded)
            self._remove_filter_value(tokens, field, value)
            self._add_filter_value(tokens.excluded, field, value)
        else:
            # Case 3: Active and inverted -> Remove it completely
            self._remove_filter_value(tokens, field, value)

    def _remove_filter_value(self, tokens: SearchTokens, field: str, value: str):
        """Remove a filter value from both included and excluded tokens."""
        for collection in [tokens.included, tokens.excluded]:
            if field in collection and value in collection[field]:
                collection[field].remove(value)
                if not collection[field]:
                    del collection[field]

    def _add_filter_value(
        self, collection: Dict[str, List[str]], field: str, value: str
    ):
        """Add a filter value to a collection (included or excluded)."""
        if field not in collection:
            collection[field] = []
        if value not in collection[field]:
            collection[field].append(value)


def apply_search(queryset, query: str, **kwargs):
    """
    Apply advanced search filters to a queryset based on parsed search tokens.

    Uses AND logic between different field filters for precise filtering.

    Supported search fields:
    - in:inbox, in:next, in:waiting, in:someday, in:reference, in:project, in:completed, in:cancelled
    - is:overdue, is:due, is:today, is:soon, is:active, is:completed, is:actionable
    - has:due, has:project, has:context, has:area, has:description
    - priority:low, priority:normal, priority:high, priority:urgent
    - due:today, due:tomorrow, due:+3days, due:-1week
    - project:"Project Name" or project:123 (id)
    - context:"@office", area:"Work"
    - waiting:"Person Name"
    """

    if not query.strip():
        return queryset

    parser = SearchParser(**kwargs)
    tokens = parser.parse(query)

    # Build combined filter using AND logic between different fields
    combined_filter = None
    combined_exclude = Q()

    # Apply included filters (AND between different fields, OR within same field)
    for _field, values in tokens.included.items():
        field_filter = _build_field_filter(_field, values)
        if field_filter:
            if combined_filter is None:
                combined_filter = field_filter
            else:
                combined_filter &= field_filter

    # Apply excluded filters
    for _field, values in tokens.excluded.items():
        field_exclude = _build_field_filter(_field, values)
        if field_exclude:
            combined_exclude |= field_exclude

    # Apply the combined filters
    if combined_filter:
        queryset = queryset.filter(combined_filter)

    if combined_exclude:
        queryset = queryset.exclude(combined_exclude)

    # Apply free text search
    if tokens.query:
        queryset = queryset.filter(
            Q(title__icontains=tokens.query)
            | Q(description__icontains=tokens.query)
            | Q(waiting_for_person__icontains=tokens.query)
        )

    return queryset


def _build_field_filter(field_name: str, values: list) -> Q:
    """Build a Q object for a specific field with OR logic for multiple values."""
    from datetime import timedelta

    from django.utils import timezone

    from .constants import GTDStatus, Priority

    field_q = Q()

    for value in values:
        value = value.lower().strip()

        if field_name == "in":
            # Status-based filters
            status_map = {
                "inbox": GTDStatus.INBOX,
                "next": GTDStatus.NEXT_ACTION,
                "action": GTDStatus.NEXT_ACTION,
                "waiting": GTDStatus.WAITING_FOR,
                "someday": GTDStatus.SOMEDAY_MAYBE,
                "maybe": GTDStatus.SOMEDAY_MAYBE,
                "reference": GTDStatus.REFERENCE,
                "project": GTDStatus.PROJECT,
                "completed": GTDStatus.COMPLETED,
                "cancelled": GTDStatus.CANCELLED,
                "canceled": GTDStatus.CANCELLED,
            }
            if value in status_map:
                field_q |= Q(status=status_map[value])

        elif field_name == "is":
            # State-based filters
            now = timezone.now()
            today = now.date()

            if value == "overdue":
                field_q |= Q(due_date__lt=now, is_completed=False)
            elif value == "due":
                field_q |= Q(due_date__date=today, is_completed=False)
            elif value == "today":
                field_q |= Q(due_date__date=today, is_completed=False)
            elif value == "soon":
                soon_date = now + timedelta(days=3)
                field_q |= Q(
                    due_date__lte=soon_date, due_date__gte=now, is_completed=False
                )
            elif value == "active":
                field_q |= ~Q(
                    status__in=[
                        GTDStatus.COMPLETED,
                        GTDStatus.CANCELLED,
                        GTDStatus.REFERENCE,
                    ]
                )
            elif value == "completed":
                field_q |= Q(is_completed=True)
            elif value == "actionable":
                field_q |= Q(status__in=[GTDStatus.NEXT_ACTION, GTDStatus.PROJECT])

        elif field_name == "has":
            # Existence-based filters
            if value == "due":
                field_q |= Q(due_date__isnull=False)
            elif value == "project":
                field_q |= Q(parent__isnull=False)
            elif value == "context":
                field_q |= Q(contexts__isnull=False)
            elif value == "area":
                field_q |= Q(area__isnull=False)
            elif value == "description":
                field_q |= ~Q(description="")

        elif field_name == "priority":
            # Priority-based filters
            priority_map = {
                "low": Priority.LOW,
                "normal": Priority.NORMAL,
                "high": Priority.HIGH,
                "urgent": Priority.URGENT,
            }
            if value in priority_map:
                field_q |= Q(priority=priority_map[value])
            elif value.startswith("-"):
                # Handle negative priority values like "-low"
                neg_value = value[1:]
                if neg_value in priority_map:
                    field_q |= ~Q(priority=priority_map[neg_value])
        elif field_name == "id":
            # ID-based filters
            try:
                item_id = int(value)
                field_q |= Q(id=item_id)
            except (ValueError, TypeError):
                pass
        elif field_name == "energy":
            # Energy filters
            energy_map = {
                "low": GTDEnergy.LOW,
                "normal": None,
                "high": GTDEnergy.HIGH,
                "medium": GTDEnergy.MEDIUM,
            }
            if value in energy_map:
                field_q |= Q(energy=energy_map[value])
            elif value.startswith("-"):
                # Handle negative energy values like "-low"
                neg_value = value[1:]
                if neg_value in energy_map:
                    field_q |= ~Q(energy=energy_map[neg_value])
        elif field_name == "due":
            # Date-based filters
            now = timezone.now()
            today = now.date()

            if value == "today":
                field_q |= Q(due_date__date=today)
            elif value == "tomorrow":
                tomorrow = today + timedelta(days=1)
                field_q |= Q(due_date__date=tomorrow)
            elif value.startswith("+") or value.startswith("-"):
                # Parse relative dates like "+3days", "-1week"
                try:
                    sign = 1 if value.startswith("+") else -1
                    value_part = value[1:]

                    if value_part.endswith("day") or value_part.endswith("days"):
                        days = int(value_part.replace("day", "").replace("s", ""))
                        target_date = today + timedelta(days=sign * days)
                        field_q |= Q(due_date__date=target_date)
                    elif value_part.endswith("week") or value_part.endswith("weeks"):
                        weeks = int(value_part.replace("week", "").replace("s", ""))
                        target_date = today + timedelta(weeks=sign * weeks)
                        field_q |= Q(due_date__date=target_date)
                except (ValueError, AttributeError):
                    pass

        elif field_name == "project":
            # Project name search or id
            try:
                item_id = int(value)
                field_q |= Q(id=item_id, status=GTDStatus.PROJECT)
                field_q |= Q(parent__id=item_id)
            except (ValueError, TypeError):
                field_q |= Q(parent__title__icontains=value)
        elif field_name == "tag":
            # Project name search
            field_q |= Q(tags__name=value)

            if value.startswith("-"):
                neg_value = value[1:]
                field_q |= ~Q(tags__name=neg_value)
            else:
                field_q |= Q(tags__name=value)

        elif field_name == "parent":
            # Parent project ID search
            try:
                parent_id = int(value)
                field_q |= Q(parent__id=parent_id)
            except (ValueError, TypeError):
                # If not a valid integer, treat as name search
                field_q |= Q(parent__title__icontains=value)

        elif field_name == "context":
            # Context search
            try:
                parent_id = int(value)
                field_q |= Q(contexts__id=parent_id)
            except (ValueError, TypeError):
                # If not a valid integer, treat as name search
                clean_value = value.lstrip("@#!")  # Remove context prefixes
                field_q |= Q(contexts__name__icontains=clean_value)

        elif field_name == "area":
            try:
                parent_id = int(value)
                field_q |= Q(area__id=parent_id)
            except (ValueError, TypeError):
                # If not a valid integer, treat as name search
                clean_value = value.lstrip("@#!")  # Remove context prefixes
                field_q |= Q(area__name__iexact=clean_value)

        elif field_name == "waiting":
            # Waiting for person search
            field_q |= Q(waiting_for_person__icontains=value)

        elif field_name == "tags":
            # Tag search (alias for context)
            clean_value = value.lstrip("@#!")
            field_q |= Q(contexts__name__icontains=clean_value)

    return field_q


def _apply_field_filter(queryset, field_name: str, values: list, exclude: bool = False):
    """Apply a specific field filter to the queryset."""
    from datetime import timedelta

    from django.db.models import Q
    from django.utils import timezone

    from .constants import GTDStatus, Priority

    # Build separate Q objects for inclusion and exclusion
    include_q = Q()
    exclude_q = Q()

    for value in values:
        value = value.lower().strip()

        # Determine if this specific value should be included or excluded
        # based on the exclude parameter passed to this function
        target_q = exclude_q if exclude else include_q

        if field_name == "in":
            # Status-based filters
            status_map = {
                "inbox": GTDStatus.INBOX,
                "next": GTDStatus.NEXT_ACTION,
                "action": GTDStatus.NEXT_ACTION,
                "waiting": GTDStatus.WAITING_FOR,
                "someday": GTDStatus.SOMEDAY_MAYBE,
                "maybe": GTDStatus.SOMEDAY_MAYBE,
                "reference": GTDStatus.REFERENCE,
                "project": GTDStatus.PROJECT,
                "completed": GTDStatus.COMPLETED,
                "cancelled": GTDStatus.CANCELLED,
                "canceled": GTDStatus.CANCELLED,
            }
            if value in status_map:
                target_q |= Q(status=status_map[value])

        elif field_name == "is":
            # State-based filters
            now = timezone.now()
            today = now.date()

            if value == "overdue":
                target_q |= Q(due_date__lt=now, is_completed=False)
            elif value == "due":
                target_q |= Q(due_date__date=today, is_completed=False)
            elif value == "today":
                target_q |= Q(due_date__date=today, is_completed=False)
            elif value == "soon":
                soon_date = now + timedelta(days=3)
                target_q |= Q(
                    due_date__lte=soon_date, due_date__gte=now, is_completed=False
                )
            elif value == "active":
                target_q |= ~Q(
                    status__in=[
                        GTDStatus.COMPLETED,
                        GTDStatus.CANCELLED,
                        GTDStatus.REFERENCE,
                    ]
                )
            elif value == "completed":
                target_q |= Q(is_completed=True)
            elif value == "actionable":
                target_q |= Q(status__in=[GTDStatus.NEXT_ACTION, GTDStatus.PROJECT])

        elif field_name == "has":
            # Existence-based filters
            if value == "due":
                target_q |= Q(due_date__isnull=False)
            elif value == "project":
                target_q |= Q(parent__isnull=False)
            elif value == "context":
                target_q |= Q(contexts__isnull=False)
            elif value == "area":
                target_q |= Q(area__isnull=False)
            elif value == "description":
                target_q |= ~Q(description="")

        elif field_name == "priority":
            # Priority-based filters
            value = value.lower()
            priority_map = {
                "low": Priority.LOW,
                "normal": Priority.NORMAL,
                "high": Priority.HIGH,
                "urgent": Priority.URGENT,
            }
            if value in priority_map:
                target_q |= Q(priority=priority_map[value])
            elif value.startswith("-"):
                # Handle negative priority values like "-low"
                neg_value = value[1:]
                if neg_value in priority_map:
                    # For negative values, we always exclude regardless of the exclude flag
                    exclude_q |= Q(priority=priority_map[neg_value])

        elif field_name == "due":
            # Date-based filters
            now = timezone.now()
            today = now.date()

            if value == "today":
                target_q |= Q(due_date__date=today)
            elif value == "tomorrow":
                tomorrow = today + timedelta(days=1)
                target_q |= Q(due_date__date=tomorrow)
            elif value.startswith("+") or value.startswith("-"):
                # Parse relative dates like "+3days", "-1week"
                try:
                    sign = 1 if value.startswith("+") else -1
                    value_part = value[1:]

                    if value_part.endswith("day") or value_part.endswith("days"):
                        days = int(value_part.replace("day", "").replace("s", ""))
                        target_date = today + timedelta(days=sign * days)
                        target_q |= Q(due_date__date=target_date)
                    elif value_part.endswith("week") or value_part.endswith("weeks"):
                        weeks = int(value_part.replace("week", "").replace("s", ""))
                        target_date = today + timedelta(weeks=sign * weeks)
                        target_q |= Q(due_date__date=target_date)
                except (ValueError, AttributeError):
                    pass

        elif field_name == "project":
            # Project name search
            target_q |= Q(parent__title__icontains=value)

        elif field_name == "parent":
            # Parent project ID search
            try:
                parent_id = int(value)
                target_q |= Q(parent__id=parent_id)
            except (ValueError, TypeError):
                # If not a valid integer, treat as name search
                target_q |= Q(parent__title__icontains=value)

        elif field_name == "context":
            # Context search
            clean_value = value.lstrip("@#!")  # Remove context prefixes
            target_q |= Q(contexts__name__icontains=clean_value)

        elif field_name == "area":
            # Area search
            target_q |= Q(area__name__icontains=value)

        elif field_name == "waiting":
            # Waiting for person search
            target_q |= Q(waiting_for_person__icontains=value)

        elif field_name == "tags":
            # Tag search (alias for context)
            clean_value = value.lstrip("@#!")
            target_q |= Q(contexts__name__icontains=clean_value)

    # Apply the filters
    if include_q:
        queryset = queryset.filter(include_q)

    if exclude_q:
        queryset = queryset.exclude(exclude_q)

    return queryset
