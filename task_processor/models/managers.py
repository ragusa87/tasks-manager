# gtd/models/managers.py
from datetime import timedelta

from django.db import models
from django.utils import timezone

from task_processor.constants import GTDConfig, GTDStatus, Priority


class GTDQuerySet(models.QuerySet):
    """Custom QuerySet with GTD-specific filters"""

    def for_user(self, user):
        return self.filter(user=user)

    def active(self):
        """Items that are in active workflow"""

        return self.exclude(
            status__in=[GTDStatus.COMPLETED, GTDStatus.CANCELLED, GTDStatus.REFERENCE]
        )

    def actionable(self):
        """Items that can be acted upon immediately"""

        return self.filter(status__in=[GTDStatus.NEXT_ACTION, GTDStatus.PROJECT])

    def overdue(self):
        """Items that are past their due date"""
        now = timezone.now()
        return self.filter(due_date__lt=now, is_completed=False).exclude(
            status__in=["completed", "cancelled"]
        )

    def due_soon(self, days=1):
        """Items due within specified days"""
        future_date = timezone.now() + timedelta(days=days)
        return self.filter(due_date__lte=future_date, is_completed=False).exclude(
            status__in=["completed", "cancelled"]
        )

    def by_priority(self, priority=None):
        """Filter by priority level"""
        if priority:
            return self.filter(priority=priority)
        return self.order_by("-priority")

    def by_context(self, context):
        """Filter by context"""
        return self.filter(context=context)

    def by_area(self, area):
        """Filter by area of responsibility"""
        return self.filter(area=area)


class ItemManager(models.Manager):
    """Enhanced manager for GTD Items with common queries"""

    def get_queryset(self):
        return GTDQuerySet(self.model, using=self._db)

    def for_user(self, user):
        """Get all items for a specific user"""
        return self.get_queryset().for_user(user)

    def inbox_items(self, user):
        """Get all unprocessed inbox items"""

        return self.for_user(user).filter(status=GTDStatus.INBOX)

    def next_actions(self, user, context=None, area=None):
        """Get actionable next actions, optionally filtered by context/area"""

        queryset = self.for_user(user).filter(
            status=GTDStatus.NEXT_ACTION, is_completed=False
        )
        if context:
            queryset = queryset.filter(context=context)
        if area:
            queryset = queryset.filter(area=area)
        return queryset

    def waiting_for(self, user, needs_follow_up=False):
        """Get waiting for items, optionally only those needing follow-up"""

        queryset = self.for_user(user).filter(status=GTDStatus.WAITING_FOR)
        if needs_follow_up:
            today = timezone.now().date()
            queryset = queryset.filter(follow_up_date__lte=today)
        return queryset

    def projects(self, user, active_only=True):
        """Get projects, optionally only active ones"""

        queryset = self.for_user(user).filter(status=GTDStatus.PROJECT)
        if active_only:
            queryset = queryset.filter(is_completed=False)
        return queryset

    def someday_maybe(self, user):
        """Get someday/maybe items"""

        return self.for_user(user).filter(status=GTDStatus.SOMEDAY_MAYBE)

    def reference_items(self, user):
        """Get reference materials"""

        return self.for_user(user).filter(status=GTDStatus.REFERENCE)

    def completed_items(self, user, days=None):
        """Get completed items, optionally within last N days"""

        queryset = self.for_user(user).filter(status=GTDStatus.COMPLETED)
        if days:
            since_date = timezone.now() - timedelta(days=days)
            queryset = queryset.filter(completed_at__gte=since_date)
        return queryset

    def overdue_items(self, user):
        """Get overdue items for a user"""

        now = timezone.now()
        return self.for_user(user).filter(
            due_date__lt=now,
            is_completed=False,
            status__in=[GTDStatus.NEXT_ACTION, GTDStatus.PROJECT],
        )

    def due_today(self, user):
        """Get items due today"""

        today = timezone.now().date()
        return self.for_user(user).filter(
            due_date__date=today,
            is_completed=False,
            status__in=[GTDStatus.NEXT_ACTION, GTDStatus.PROJECT],
        )

    def due_this_week(self, user):
        """Get items due this week"""

        today = timezone.now().date()
        week_end = today + timedelta(days=7)
        return self.for_user(user).filter(
            due_date__date__range=[today, week_end],
            is_completed=False,
            status__in=[GTDStatus.NEXT_ACTION, GTDStatus.PROJECT],
        )

    def high_priority(self, user):
        """Get high and urgent priority items"""
        return (
            self.for_user(user)
            .filter(priority__in=[Priority.HIGH, Priority.URGENT], is_completed=False)
            .active()
        )

    def get_dashboard_data(self, user):
        """Get comprehensive dashboard data for a user"""
        return {
            "inbox_count": self.inbox_items(user).count(),
            "next_actions_count": self.next_actions(user).count(),
            "waiting_for_count": self.waiting_for(user).count(),
            "projects_count": self.projects(user).count(),
            "someday_maybe_count": self.someday_maybe(user).count(),
            "overdue_count": self.overdue_items(user).count(),
            "due_today_count": self.due_today(user).count(),
            "high_priority_count": self.high_priority(user).count(),
        }

    def needs_review(self, user):
        """Get items that need review (someday/maybe items)"""
        someday_items = self.someday_maybe(user)
        return [item for item in someday_items if item.needs_review]

    def needs_follow_up(self, user):
        """Get waiting for items that need follow-up"""
        waiting_items = self.waiting_for(user)
        return [item for item in waiting_items if item.needs_follow_up]

    def get_context_summary(self, user):
        """Get summary of items by context"""

        return (
            self.for_user(user)
            .filter(
                status__in=[GTDStatus.NEXT_ACTION, GTDStatus.PROJECT],
                is_completed=False,
            )
            .values("context__name")
            .annotate(count=models.Count("id"))
            .order_by("-count")
        )

    def get_area_summary(self, user):
        """Get summary of items by area"""

        return (
            self.for_user(user)
            .filter(
                status__in=[GTDStatus.NEXT_ACTION, GTDStatus.PROJECT],
                is_completed=False,
            )
            .values("area__name")
            .annotate(count=models.Count("id"))
            .order_by("-count")
        )


class ContextManager(models.Manager):
    """Manager for Context model"""

    def for_user(self, user):
        return self.filter(user=user)

    def with_item_counts(self, user):
        """Get contexts with count of active items"""

        return (
            self.for_user(user)
            .annotate(
                item_count=models.Count(
                    "item",
                    filter=models.Q(
                        item__status__in=[GTDStatus.NEXT_ACTION, GTDStatus.PROJECT],
                        item__is_completed=False,
                    ),
                )
            )
            .order_by("name")
        )

    def create_defaults_for_user(self, user):
        """Create default contexts for a new user"""
        for context_name in GTDConfig.DEFAULT_CONTEXTS:
            self.get_or_create(
                name=context_name,
                user=user,
                defaults={"description": f"Default {context_name} context"},
            )


class AreaManager(models.Manager):
    """Manager for Area model"""

    def for_user(self, user):
        return self.filter(user=user)

    def with_item_counts(self, user):
        """Get areas with count of active items"""

        return (
            self.for_user(user)
            .annotate(
                item_count=models.Count(
                    "item",
                    filter=models.Q(
                        item__status__in=[GTDStatus.NEXT_ACTION, GTDStatus.PROJECT],
                        item__is_completed=False,
                    ),
                )
            )
            .order_by("name")
        )

    def create_defaults_for_user(self, user):
        """Create default areas for a new user"""
        for area_name in GTDConfig.DEFAULT_AREAS:
            self.get_or_create(
                name=area_name,
                user=user,
                defaults={"description": f"Default {area_name} area"},
            )
