import re
from dataclasses import dataclass, field
from typing import Dict, List
from django.db.models import Q


@dataclass
class SearchTokens:
    original_query: str
    included: Dict[str, List[str]] = field(default_factory=dict)
    excluded: Dict[str, List[str]] = field(default_factory=dict)
    query: str = ""


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
            if ',' in value_string:
                values.extend([v.strip() for v in value_string.split(',') if v.strip()])
            else:
                values.append(value_string)

        return values

    def _clean_remaining_query(self, remaining: str) -> str:
        """Clean up the remaining query string."""
        # Remove extra whitespace
        cleaned = re.sub(r'\s+', ' ', remaining).strip()

        # Remove standalone quotes that might be left over
        cleaned = re.sub(r'(?:^|\s)"(?:\s|$)', ' ', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        return (cleaned + " " + self.forced_query).strip()

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
    - project:"Project Name"
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
            Q(title__icontains=tokens.query) |
            Q(description__icontains=tokens.query)
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
                field_q |= Q(due_date__lte=soon_date, due_date__gte=now, is_completed=False)
            elif value == "active":
                field_q |= ~Q(status__in=[GTDStatus.COMPLETED, GTDStatus.CANCELLED, GTDStatus.REFERENCE])
            elif value == "completed":
                field_q |= Q(is_completed=True)
            elif value == "actionable":
                field_q |= Q(status__in=[GTDStatus.NEXT_ACTION, GTDStatus.PROJECT])

        elif field_name == "has":
            # Existence-based filters
            if value == "due":
                field_q |= Q(due_date__isnull=False)
            elif value == "project":
                field_q |= Q(parent_project__isnull=False)
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
            # Project name search
            field_q |= Q(parent_project__title__icontains=value)

        elif field_name == "context":
            # Context search
            clean_value = value.lstrip("@#!")  # Remove context prefixes
            field_q |= Q(contexts__name__icontains=clean_value)

        elif field_name == "area":
            # Area search
            field_q |= Q(area__name__icontains=value)

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
                target_q |= Q(due_date__lte=soon_date, due_date__gte=now, is_completed=False)
            elif value == "active":
                target_q |= ~Q(status__in=[GTDStatus.COMPLETED, GTDStatus.CANCELLED, GTDStatus.REFERENCE])
            elif value == "completed":
                target_q |= Q(is_completed=True)
            elif value == "actionable":
                target_q |= Q(status__in=[GTDStatus.NEXT_ACTION, GTDStatus.PROJECT])

        elif field_name == "has":
            # Existence-based filters
            if value == "due":
                target_q |= Q(due_date__isnull=False)
            elif value == "project":
                target_q |= Q(parent_project__isnull=False)
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
            target_q |= Q(parent_project__title__icontains=value)

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
