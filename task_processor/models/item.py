# gtd/models/item.py
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.module_loading import import_string
from django.utils.translation import gettext_lazy as _
from viewflow import fsm

from task_processor.constants import GTDConfig, GTDEnergy, GTDStatus, Priority

from .base_models import Area, Context, Tag


def requires_form(form_class):
    """
    Decorator for ItemFlow transitions that require a form.

    Args:
        form_class: The Django form class to use for this transition (can be a string path)
    """
    def decorator(func):
        func._form_class = form_class
        return func
    return decorator

def priority(position: int = 0):
    def decorator(func):
        func._position = position
        return func
    return decorator



class ItemTransition(dict):
    @property
    def name(self):
        return self.get("name")
    @property
    def label(self):
        return self.get("label")
    @property
    def form_class(self):
        return self.get("form_class")

class ItemTransitionsBag(list[ItemTransition]):
    @staticmethod
    def sort_by_priority(x: ItemTransition):
        p = x.get('position')
        if p is None:
            p = 0
        if p > 0:
            return (0, -p)  # positives, highest first
        if p == 0:
            return (1, 0)  # None/0, middle
        return (2, -p)  # negatives, closer to 0 first

    def __init__(self, seq=()):
        # Sort by priority (higher numbers first, None values as zero)
        sorted_seq = sorted(seq, key=ItemTransitionsBag.sort_by_priority)
        super().__init__(sorted_seq)
    def get_transition(self, transition_slug):
        # Check if the requested transition is allowed
        for trans in self:
            if trans.name == transition_slug:
                return trans
        return None

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
            queryset = queryset.filter(contexts=context)
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
    title = models.CharField(max_length=1024)
    description = models.TextField(blank=True)

    # State machine field - this enforces valid transitions
    status = models.CharField(max_length=50, choices=GTDStatus.choices, default=GTDStatus.INBOX)
    energy = models.CharField(max_length=10, choices=GTDEnergy.choices, default=None, null=True)

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
    contexts = models.ManyToManyField(Context, blank=True)
    area = models.ForeignKey(Area, on_delete=models.SET_NULL, null=True, blank=True)
    tags = models.ManyToManyField(Tag, blank=True)

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

    # External integrations
    nirvana_id = models.CharField(max_length=100, null=True, blank=True, unique=True,
                                  help_text="External Nirvana ID for syncing")

    # Metadata
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ItemManager()

    class Meta:
        ordering = ['-priority', 'due_date', 'created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['user', 'status', 'is_completed']),
            models.Index(fields=['due_date']),
            models.Index(fields=['area']),
            models.Index(fields=['nirvana_id']),
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
    def is_reference(self):
        return self.status == GTDStatus.REFERENCE

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

    @property
    def priority_icon(self):
        """Get priority icon name for sprite tags"""
        return GTDConfig.PRIORITY_ICONS.get(self.priority, '')

    @property
    def priority_color(self):
        """Get priority color class for styling"""
        return GTDConfig.PRIORITY_COLORS.get(self.priority, 'text-gray-500')

    # Property to get the flow instance
    @property
    def flow(self):
        """Get the ItemFlow instance for this item"""
        return ItemFlow(self)

    # Custom validation for state-specific fields
    def clean(self):
        super().clean()

        # Validate waiting_for fields
        if self.status == GTDStatus.WAITING_FOR:
            if not self.waiting_for_person or str(self.waiting_for_person).strip() == "":
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
    def get_available_transitions(self) ->ItemTransitionsBag:
        """Get list of available state transitions for current state"""
        return self.flow.get_available_transitions()

    # Get all transitions for UI
    def get_all_transitions(self) -> ItemTransitionsBag:
        """Get list of available state transitions for current state"""
        return self.flow.get_all_transitions()


class ItemFlow:
    """
    Flow class for GTD Item state machine using viewflow.fsm
    """
    state_field = fsm.State(GTDStatus, default=GTDStatus.INBOX)

    state_icon_mapping = {
        GTDStatus.INBOX.value: ('lucide-inbox', '📥'),
        GTDStatus.NEXT_ACTION.value: ('lucide-zap', '🚀'),
        GTDStatus.WAITING_FOR.value: ('lucide-hourglass', '👤'),
        GTDStatus.SOMEDAY_MAYBE.value: ('lucide-history', '💭'),
        GTDStatus.REFERENCE.value: ('lucide-archive', '📁'),
        GTDStatus.PROJECT.value: ('lucide-briefcase', '💼'),
        GTDStatus.COMPLETED.value: ('lucide-badge-check', '✅'),
        GTDStatus.CANCELLED.value: ('lucide-trash-2', '🚫'),
    }

    def __init__(self, item):
        self.item = item

    @state_field.setter()
    def _set_item_status(self, value):
        self.item.status = value

    @state_field.getter()
    def _get_item_status(self):
        return self.item.status

    # State Machine Transitions with Guards and Actions
    @state_field.transition(source=GTDStatus.INBOX, target=GTDStatus.NEXT_ACTION, label=_("Next Action"))
    def process_as_action(self):
        """Process inbox item as actionable task"""
        pass

    @state_field.transition(source=GTDStatus.INBOX, target=GTDStatus.PROJECT, label=_("Convert to Project"))
    def process_as_project(self):
        """Process inbox item as multi-step project"""
        pass

    @state_field.transition(source=GTDStatus.INBOX, target=GTDStatus.SOMEDAY_MAYBE, label=_("Someday/Maybe"))
    def process_as_someday_maybe(self):
        """Process inbox item as someday/maybe"""
        if not self.item.last_reviewed:
            self.item.last_reviewed = timezone.now().date()

    @state_field.transition(source=GTDStatus.INBOX, target=GTDStatus.REFERENCE,label=_("Convert as Reference"))
    def process_as_reference(self):
        """Process inbox item as reference material"""
        pass

    @requires_form("task_processor.forms.WaitingForForm")
    @state_field.transition(source=[GTDStatus.NEXT_ACTION], target=GTDStatus.WAITING_FOR, label=_("Waiting For"))
    def delegate(self, person, follow_up_days=None):
        """Delegate task to someone else"""
        if person:
            self.item.waiting_for_person = person
        if not self.item.date_requested:
            self.item.date_requested = timezone.now().date()
        if not self.item.follow_up_date:
            days = follow_up_days or GTDConfig.DEFAULT_FOLLOW_UP_DAYS
            self.item.follow_up_date = timezone.now().date() + timedelta(days=days)

    @state_field.transition(source=[GTDStatus.NEXT_ACTION, GTDStatus.WAITING_FOR],
                           target=GTDStatus.SOMEDAY_MAYBE, label=_("Someday/Maybe"))
    def defer_to_someday_maybe(self):
        """Move active item to someday/maybe"""
        if not self.item.last_reviewed:
            self.item.last_reviewed = timezone.now().date()

    @state_field.transition(source=GTDStatus.SOMEDAY_MAYBE, target=GTDStatus.NEXT_ACTION, label=_("Next Action"))
    def activate_from_someday_maybe(self):
        """Activate someday/maybe item as next action"""
        pass

    @state_field.transition(source=GTDStatus.SOMEDAY_MAYBE, target=GTDStatus.PROJECT, label=_("Convert to Project"))
    def activate_as_project(self):
        """Activate someday/maybe item as project"""
        pass

    @state_field.transition(source=GTDStatus.WAITING_FOR, target=GTDStatus.NEXT_ACTION, label=_("Received Response"))
    def receive_response(self):
        """Mark waiting for item as received/resolved"""
        pass

    @state_field.transition(source=[GTDStatus.NEXT_ACTION, GTDStatus.PROJECT], target=GTDStatus.COMPLETED, label=_("Complete"))
    def complete(self):
        """Mark item as completed"""
        self.item.is_completed = True
        self.item.completed_at = timezone.now()

    @priority(-100)
    @state_field.transition(source=fsm.State.ANY, target=GTDStatus.CANCELLED, conditions=[lambda self: not self.item.status == GTDStatus.CANCELLED], label=_("Cancel"))
    def cancel(self):
        """Cancel item from any state"""
        pass

    @state_field.transition(source=GTDStatus.CANCELLED, target=GTDStatus.INBOX, label=_("Restore to Inbox"))
    def uncancel(self):
        """Process inbox item as actionable task"""
        pass

    @state_field.transition(source=GTDStatus.COMPLETED, target=GTDStatus.NEXT_ACTION,
                           conditions=[lambda self: self.item.is_completed], label=_("Reopen"))
    def reopen(self):
        """Reopen completed item"""
        self.item.is_completed = False
        self.item.completed_at = None

    @state_field.on_success()
    def _on_transition_success(self, descriptor, source, target, **kwargs):
        """Save the item after successful transition"""
        self.item.save()

    def get_all_transitions(self) -> ItemTransitionsBag:
        # Get all transition methods by checking for the viewflow transition decorator
        transitions = []
        for method_name in dir(self):
            if method_name.startswith('_'):
                continue
            method = getattr(self, method_name)
            if hasattr(method, 'get_transitions'):
                method_transitions = method.get_transitions()
                for transition in method_transitions:
                    transitions.append(self._transition_to_dict(transition))
        return ItemTransitionsBag(transitions)

    def _get_annotated_property(self, transition_slug: str, property_name = "_form_class"):
        # Get the original function from the class to check for decorator attributes
        original_func = getattr(self.__class__, transition_slug)

        # The decorator attributes are preserved on the _descriptor object
        property_value = None
        if hasattr(original_func, '_descriptor'):
            descriptor = original_func._descriptor
            property_value = getattr(descriptor, property_name, None)

        if not property_value:
            return None

        # Import the form class if it's a string path
        if property_name == '_form_class' and isinstance(property_value, str):
            return import_string(property_value)
        return property_value

    def _transition_to_dict(self, transition) -> ItemTransition:
        transition_slug = str(transition.slug)
        transition_target = str(transition.target)
        sprite_icon_tuple = self.state_icon_mapping.get(transition_target, (None, None))

        return ItemTransition(**{
            'name': transition_slug,
            'label': str(transition.label),
            'source': str(transition.source),
            'target': str(transition.target),
            'sprite': sprite_icon_tuple[0],
            'icon': sprite_icon_tuple[1],
            'form_class': self._get_annotated_property(transition_slug),
            'position': self._get_annotated_property(transition_slug, "_position"),
        })

    @property
    def icon(self):
        return self._get_icon(index=1)

    @property
    def sprite(self):
        return self._get_icon()

    def _get_icon(self, index=0):
        """Get icon for current state"""
        index = max(0, min(index, 1))  # Clamp index to 0 or 1
        return self.state_icon_mapping.get(self.item.status, (None, None))[index]
    def get_available_transitions(self) -> ItemTransitionsBag:
        """Get list of available state transitions for current state"""
        transitions = []

        # Get all transition methods by checking for the viewflow transition decorator
        for method_name in dir(self):
            if method_name.startswith('_'):
                continue

            method = getattr(self, method_name)
            if hasattr(method, 'get_transitions'):
                # Check if this transition can proceed from current state
                if hasattr(method, 'can_proceed') and method.can_proceed():
                    # Get the transition details
                    method_transitions = method.get_transitions()
                    for transition in method_transitions:
                        transitions.append(self._transition_to_dict(transition))
                        break  # Usually only one transition per method

        return ItemTransitionsBag(transitions)