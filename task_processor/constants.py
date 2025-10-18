from django.db import models


class GTDStatus(models.TextChoices):
    """GTD Item Status States"""

    INBOX = "inbox", "Inbox"
    NEXT_ACTION = "next_action", "Next Action"
    WAITING_FOR = "waiting_for", "Waiting For"
    SOMEDAY_MAYBE = "someday_maybe", "Someday/Maybe"
    REFERENCE = "reference", "Reference"
    PROJECT = "project", "Project"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class GTDEnergy(models.TextChoices):
    HIGH = "high", "High Energy"
    MEDIUM = "medium", "Medium Energy"
    LOW = "low", "Low Energy"


class GTDDuration(models.TextChoices):
    QUICK = "quick", "Quick (≤2 min)"
    SHORT = "short", "Short (15-30 min)"
    MEDIUM = "medium", "Medium (1-2 hours)"
    LONG = "long", "Long (3+ hours)"


class Priority(models.IntegerChoices):
    """Task Priority Levels"""

    LOW = 1, "Low"
    NORMAL = 2, "Normal"
    HIGH = 3, "High"
    URGENT = 4, "Urgent"


class ReviewType(models.TextChoices):
    """GTD Review Types"""

    WEEKLY = "weekly", "Weekly Review"
    MONTHLY = "monthly", "Monthly Review"
    QUARTERLY = "quarterly", "Quarterly Review"
    ANNUAL = "annual", "Annual Review"


class GTDConfig:
    """GTD System Configuration Constants"""

    DEFAULT_FOLLOW_UP_DAYS = 7
    DEFAULT_SOMEDAY_MAYBE_REVIEW_DAYS = 90
    DEFAULT_WAITING_FOR_REVIEW_DAYS = 14
    MAX_DEPTH = 2  # Maximum nesting level for projects/references
    OVERDUE_WARNING_DAYS = 1  # Days before due date to show warning
    MAX_REMINDER_THRESHOLD = 10  # Maximum retry attempts for failed reminders

    STATUS_WITH_PARENT_ALLOWED = [
        GTDStatus.PROJECT,
        GTDStatus.REFERENCE,
    ]

    # Default contexts
    DEFAULT_CONTEXTS = [
        "home",
        "office",
        "phone",
        "computer",
        "errands",
        "online",
        "agenda",
    ]

    # Default areas
    DEFAULT_AREAS = [
        "Personal",
        "Work",
        "Health",
        "Finance",
        "Family",
        "Learning",
        "Community",
    ]

    # Review intervals in days
    REVIEW_INTERVALS = {
        ReviewType.WEEKLY: 7,
        ReviewType.MONTHLY: 30,
        ReviewType.QUARTERLY: 90,
        ReviewType.ANNUAL: 365,
    }

    # Priority indicators for UI (legacy emoji)
    PRIORITY_INDICATORS = {
        Priority.LOW: "🔵",
        Priority.NORMAL: "⚪",
        Priority.HIGH: "🟡",
        Priority.URGENT: "🔴",
    }
    PRIORITY_COLORS = {
        Priority.LOW: "text-blue-500",
        Priority.NORMAL: "text-gray-500",
        Priority.HIGH: "text-orange-500",
        Priority.URGENT: "text-red-500",
    }
    # Priority icons (Lucide sprites)
    PRIORITY_ICONS = {
        Priority.LOW: "lucide-arrow-down",
        Priority.NORMAL: "lucide-minus",
        Priority.HIGH: "lucide-arrow-up",
        Priority.URGENT: "lucide-circle-alert",
    }
