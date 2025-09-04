# gtd/constants.py
from django.db import models


class GTDStatus(models.TextChoices):
    """GTD Item Status States"""
    INBOX = 'inbox', 'Inbox'
    NEXT_ACTION = 'next_action', 'Next Action'
    WAITING_FOR = 'waiting_for', 'Waiting For'
    SOMEDAY_MAYBE = 'someday_maybe', 'Someday/Maybe'
    REFERENCE = 'reference', 'Reference'
    PROJECT = 'project', 'Project'
    COMPLETED = 'completed', 'Completed'
    CANCELLED = 'cancelled', 'Cancelled'


class Priority(models.IntegerChoices):
    """Task Priority Levels"""
    LOW = 1, 'Low'
    NORMAL = 2, 'Normal'
    HIGH = 3, 'High'
    URGENT = 4, 'Urgent'


class ReviewType(models.TextChoices):
    """GTD Review Types"""
    WEEKLY = 'weekly', 'Weekly Review'
    MONTHLY = 'monthly', 'Monthly Review'
    QUARTERLY = 'quarterly', 'Quarterly Review'
    ANNUAL = 'annual', 'Annual Review'


class GTDConfig:
    """GTD System Configuration Constants"""
    DEFAULT_FOLLOW_UP_DAYS = 7
    DEFAULT_SOMEDAY_MAYBE_REVIEW_DAYS = 90
    DEFAULT_WAITING_FOR_REVIEW_DAYS = 14
    MAX_PROJECT_DEPTH = 3  # Maximum nesting level for projects
    OVERDUE_WARNING_DAYS = 1  # Days before due date to show warning

    # Context prefixes
    CONTEXT_PREFIXES = ['@', '#', '!']

    # Default contexts
    DEFAULT_CONTEXTS = [
        '@home', '@office', '@phone', '@computer',
        '@errands', '@online', '@agenda'
    ]

    # Default areas
    DEFAULT_AREAS = [
        'Personal', 'Work', 'Health', 'Finance',
        'Family', 'Learning', 'Community'
    ]

    # Review intervals in days
    REVIEW_INTERVALS = {
        ReviewType.WEEKLY: 7,
        ReviewType.MONTHLY: 30,
        ReviewType.QUARTERLY: 90,
        ReviewType.ANNUAL: 365,
    }

    # Priority indicators for UI
    PRIORITY_INDICATORS = {
        Priority.LOW: "🔵",
        Priority.NORMAL: "⚪",
        Priority.HIGH: "🟡",
        Priority.URGENT: "🔴"
    }