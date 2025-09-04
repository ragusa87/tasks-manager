# gtd/models/item.py
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django_fsm import FSMField, transition
from django_fsm_log.decorators import fsm_log_by

from task_processor.constants import GTDConfig, GTDStatus, Priority

from .base_models import Area, Context


class ItemManager(models.Manager):
    """Custom manager for GTD items with common queries"""

    def for_user(self, user):
        return self.filter(user=user)

    def inbox_items(self, user):
        """Get all unprocessed inbox items"""
        return self.filter(user=user, status=GTDStatus.INBOX)

    def next_actions(self, user, context=None):
        """Get actionable next actions, optionally filtered by context"""
        queryset = self.filter(
            user=user,
            status=GTDStatus.NEXT_ACTION,
            is_completed=False
        )
        if context:
            queryset = queryset.filter(context=context)
        return queryset

    def waiting_for(self, user, needs_follow_up=False):
        """Get waiting for items, optionally only those needing follow-up"""
        queryset = self.filter(user=user, status=GTDStatus.WAITING_FOR)
        if needs_follow_up:
            today = timezone.now().date()
            queryset = queryset.filter(follow_up_date__lte=today)
        return queryset

    def projects(self, user, active_only=True):
        """Get projects, optionally only active ones"""
        queryset = self.filter(user=user, status=GTDStatus.PROJECT)
        if active_only:
            queryset = queryset.filter(is_completed=False)
        return queryset

    def someday_maybe(self, user, needs_review=False):
        """Get someday/maybe items, optionally only those needing review"""
        queryset = self.filter(user=user, status=GTDStatus.SOMEDAY_MAYBE)
        if needs_review:
            # Note: This requires additional filtering in Python due to complex logic
            return [item for item in queryset if item.needs_review]
        return queryset

    def overdue(self, user):
        """Get overdue items"""
        now = timezone.now()
        return self.filter(
            user=user,
            due_date__lt=now,
            is_completed=False,
            status__in=[GTDStatus.NEXT_ACTION, GTDStatus.PROJECT]
        )

    def due_today(self, user):
        """Get items due today"""
        today = timezone.now().date()
        return self.filter(
            user=user,
            due_date__date=today,
            is_completed=False,
            status__in=[GTDStatus.NEXT_ACTION, GTDStatus.PROJECT]
        )


class Item(models.Model):
    """
    Universal GTD Item with State Machine for status transitions
    """
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    # State machine field - this enforces valid transitions
    status = FSMField(default=GTDStatus.INBOX, choices=GTDStatus.choices)

    priority = models.IntegerField(choices=Priority.choices, default=Priority.NORMAL)

    # GTD-specific fields
    parent_project = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='sub_items',
        limit_choices_to={'status': GTDStatus.PROJECT}
    )
    context = models.ForeignKey(Context, on_delete=models.SET_NULL, null=True, blank=True)
    area = models.ForeignKey(Area, on_delete=models.SET_NULL, null=True, blank=True)

    # Time-related fields
    due_date = models.DateTimeField(null=True, blank=True)
    start_date = models.DateTimeField(null=True, blank=True)
    estimated_duration = models.DurationField(null=True, blank=True, help_text="Estimated time to complete")

    # Completion tracking
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Waiting For fields (used when status=WAITING_FOR)
    waiting_for_person = models.CharField(max_length=100, blank=True,
                                          help_text="Person/system this is delegated to")
    date_requested = models.DateField(null=True, blank=True,
                                      help_text="When was this requested/delegated")
    follow_up_date = models.DateField(null=True, blank=True,
                                      help_text="When to follow up")

    # Someday/Maybe fields (used when status=SOMEDAY_MAYBE)
    last_reviewed = models.DateField(null=True, blank=True)
    review_frequency_days = models.IntegerField(
        default=GTDConfig.DEFAULT_SOMEDAY_MAYBE_REVIEW_DAYS,
        help_text="How often to review this someday/maybe item"
    )

    # Metadata
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ItemManager()

    class Meta:
        ordering = ['-priority', 'due_date', 'created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['user', 'status', 'is_completed']),
            models.Index(fields=['due_date']),
            models.Index(fields=['context']),
            models.Index(fields=['area']),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Auto-set completion timestamp
        if self.is_completed and not self.completed_at:
            self.completed_at = timezone.now()
            if self.status not in [GTDStatus.COMPLETED, GTDStatus.CANCELLED]:
                self.status = GTDStatus.COMPLETED
        elif not self.is_completed:
            self.completed_at = None
            if self.status == GTDStatus.COMPLETED:
                self.status = GTDStatus.NEXT_ACTION

        super().save(*args, **kwargs)

    # Properties for different GTD contexts
    @property
    def is_project(self):
        return self.status == GTDStatus.PROJECT

    @property
    def is_task(self):
        return self.status in [GTDStatus.NEXT_ACTION, GTDStatus.WAITING_FOR, GTDStatus.INBOX]

    @property
    def is_someday_maybe(self):
        return self.status == GTDStatus.SOMEDAY_MAYBE

    @property
    def is_waiting_for(self):
        return self.status == GTDStatus.WAITING_FOR

    @property
    def is_actionable(self):
        """True if item can be acted upon immediately"""
        return self.status in [GTDStatus.NEXT_ACTION, GTDStatus.PROJECT]

    @property
    def is_active(self):
        """True if item is in active workflow"""
        return self.status not in [GTDStatus.COMPLETED, GTDStatus.CANCELLED, GTDStatus.REFERENCE]

    @property
    def is_overdue(self):
        if self.due_date and not self.is_completed:
            return timezone.now() > self.due_date
        return False

    @property
    def is_due_soon(self):
        """True if due within warning period"""
        if self.due_date and not self.is_completed:
            warning_date = timezone.now() + timedelta(days=GTDConfig.OVERDUE_WARNING_DAYS)
            return self.due_date <= warning_date
        return False

    @property
    def is_due_today(self):
        if self.due_date and not self.is_completed:
            return self.due_date.date() == timezone.now().date()
        return False

    @property
    def needs_follow_up(self):
        """For waiting_for items"""
        if self.status == GTDStatus.WAITING_FOR and self.follow_up_date:
            return timezone.now().date() >= self.follow_up_date
        return False

    @property
    def needs_review(self):
        """For someday_maybe items"""
        if self.status == GTDStatus.SOMEDAY_MAYBE:
            if not self.last_reviewed:
                return True
            days_since_review = (timezone.now().date() - self.last_reviewed).days
            return days_since_review >= self.review_frequency_days
        return False

    @property
    def project_depth(self):
        """Calculate nesting depth for projects"""
        depth = 0
        current = self.parent_project
        while current and depth < GTDConfig.MAX_PROJECT_DEPTH:
            depth += 1
            current = current.parent_project
        return depth

    @property
    def next_actions(self):
        """For project items - get their next actions"""
        if self.is_project:
            return self.sub_items.filter(
                status=GTDStatus.NEXT_ACTION,
                is_completed=False
            )
        return Item.objects.none()

    @property
    def priority_display(self):
        """Get priority display with emoji indicators"""
        return f"{GTDConfig.PRIORITY_INDICATORS.get(self.priority, '')} {self.get_priority_display()}"

    # State Machine Transitions with Guards and Actions
    @fsm_log_by
    @transition(field=status, source=GTDStatus.INBOX, target=GTDStatus.NEXT_ACTION)
    def process_as_action(self, by=None):
        """Process inbox item as actionable task"""
        pass

    @fsm_log_by
    @transition(field=status, source=GTDStatus.INBOX, target=GTDStatus.PROJECT)
    def process_as_project(self, by=None):
        """Process inbox item as multi-step project"""
        pass

    @fsm_log_by
    @transition(field=status, source=GTDStatus.INBOX, target=GTDStatus.SOMEDAY_MAYBE)
    def process_as_someday_maybe(self, by=None):
        """Process inbox item as someday/maybe"""
        if not self.last_reviewed:
            self.last_reviewed = timezone.now().date()

    @fsm_log_by
    @transition(field=status, source=GTDStatus.INBOX, target=GTDStatus.REFERENCE)
    def process_as_reference(self, by=None):
        """Process inbox item as reference material"""
        pass

    @fsm_log_by
    @transition(field=status, source=GTDStatus.INBOX, target=GTDStatus.CANCELLED)
    def process_as_trash(self, by=None):
        """Delete/trash inbox item"""
        pass

    @fsm_log_by
    @transition(field=status, source=[GTDStatus.NEXT_ACTION, GTDStatus.PROJECT], target=GTDStatus.WAITING_FOR)
    def delegate(self, person=None, follow_up_days=None, by=None):
        """Delegate task to someone else"""
        if person:
            self.waiting_for_person = person
        if not self.date_requested:
            self.date_requested = timezone.now().date()
        if not self.follow_up_date:
            days = follow_up_days or GTDConfig.DEFAULT_FOLLOW_UP_DAYS
            self.follow_up_date = timezone.now().date() + timedelta(days=days)

    @fsm_log_by
    @transition(field=status, source=[GTDStatus.NEXT_ACTION, GTDStatus.PROJECT, GTDStatus.WAITING_FOR],
                target=GTDStatus.SOMEDAY_MAYBE)
    def defer_to_someday_maybe(self, by=None):
        """Move active item to someday/maybe"""
        if not self.last_reviewed:
            self.last_reviewed = timezone.now().date()

    @fsm_log_by
    @transition(field=status, source=GTDStatus.SOMEDAY_MAYBE, target=GTDStatus.NEXT_ACTION)
    def activate_from_someday_maybe(self, by=None):
        """Activate someday/maybe item as next action"""
        pass

    @fsm_log_by
    @transition(field=status, source=GTDStatus.SOMEDAY_MAYBE, target=GTDStatus.PROJECT)
    def activate_as_project(self, by=None):
        """Activate someday/maybe item as project"""
        pass

    @fsm_log_by
    @transition(field=status, source=GTDStatus.WAITING_FOR, target=GTDStatus.NEXT_ACTION)
    def receive_response(self, by=None):
        """Mark waiting for item as received/resolved"""
        pass

    @fsm_log_by
    @transition(field=status, source=[GTDStatus.NEXT_ACTION, GTDStatus.PROJECT], target=GTDStatus.COMPLETED)
    def complete(self, by=None):
        """Mark item as completed"""
        self.is_completed = True
        self.completed_at = timezone.now()

    @fsm_log_by
    @transition(field=status, source='*', target=GTDStatus.CANCELLED)
    def cancel(self, by=None):
        """Cancel item from any state"""
        pass

    @fsm_log_by
    @transition(field=status, source=GTDStatus.COMPLETED, target=GTDStatus.NEXT_ACTION,
                conditions=['can_reopen'])
    def reopen(self, by=None):
        """Reopen completed item"""
        self.is_completed = False
        self.completed_at = None

    def can_reopen(self):
        """Guard condition for reopening completed items"""
        return self.is_completed

    # Custom validation for state-specific fields
    def clean(self):
        super().clean()

        # Validate waiting_for fields
        if self.status == GTDStatus.WAITING_FOR:
            if not self.waiting_for_person:
                raise ValidationError("Waiting for items must specify who/what you're waiting for")

        # Validate project hierarchy depth
        if self.parent_project:
            if self.parent_project.status != GTDStatus.PROJECT:
                raise ValidationError("Parent must be a project")

            if self.project_depth >= GTDConfig.MAX_PROJECT_DEPTH:
                raise ValidationError(f"Project nesting cannot exceed {GTDConfig.MAX_PROJECT_DEPTH} levels")

        # Prevent circular references
        if self.parent_project and self.status == GTDStatus.PROJECT:
            if self._check_circular_reference(self.parent_project):
                raise ValidationError(f"Circular project reference detected: {self.parent_project.pk}")

        # Validate priority for urgent items
        if self.priority == Priority.URGENT and not self.due_date:
            raise ValidationError("Urgent items should have a due date")

    def _check_circular_reference(self, potential_parent):
        """Check for circular references in project hierarchy"""
        if potential_parent == self:
            return True
        if potential_parent.parent_project:
            return self._check_circular_reference(potential_parent.parent_project)
        return False

    # Get available transitions for UI
    def get_available_transitions(self):
        """Get list of available state transitions for current state"""
        transitions = []
        for trans in self._meta.get_field('status').transitions:
            if trans.has_perm(self):
                transitions.append({
                    'name': trans.name,
                    'target': trans.target,
                    'display_name': trans.name.replace('_', ' ').title()
                })
        return transitions