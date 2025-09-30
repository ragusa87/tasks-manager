import json

from dateutil.rrule import rrulestr
from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError

from .constants import GTDConfig, GTDDuration, GTDEnergy, GTDStatus, Priority
from .models.base_models import Area, Context, Tag
from .models.item import Item, ItemFlow


class AirDatepickerMixin:
    date_format_js = 'yyyy-MM-dd'
    time_format_js = 'H:mm'
    timepicker = False
    def build_attrs(self, base_attrs, extra_attrs=None):
        attrs = (base_attrs or {}).copy()
        attrs['data-airdatepicker'] = json.dumps({'locale': 'fr', "firstDay":1,"dateFormat" : self.date_format_js, "timeFormat": self.time_format_js, "timepicker": self.timepicker})
        return super().build_attrs(attrs, extra_attrs)

class CustomDateInput(AirDatepickerMixin, forms.DateInput):
    input_type = "date"
    def __init__(self, *args, **kwargs):
        super().__init__(format=settings.DATE_INPUT_FORMAT, *args, **kwargs)

class CustomDateTimeInput(AirDatepickerMixin, forms.DateInput):
    input_type = "datetime-local"
    timepicker = True

    def __init__(self, *args, **kwargs):
        super().__init__(format=settings.DATETIME_INPUT_FORMAT, *args, **kwargs)


class RecurrenceField(forms.CharField):
    """
    Custom form field for handling RRULE recurrence patterns.
    Validates that the RRULE is properly formatted and has minimum daily frequency.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('required', False)
        kwargs.setdefault('help_text', 'Optional: Enter RRULE recurrence pattern (e.g., FREQ=DAILY;INTERVAL=1 or FREQ=WEEKLY;BYDAY=MO,WE)')
        super().__init__(*args, **kwargs)

    def clean(self, value):
        value = super().clean(value)

        if not value:
            return None

        value = value.strip()
        if not value:
            return None

        try:
            # Try to parse the RRULE
            rrule = rrulestr(value)

            # Validate minimum frequency is daily
            if hasattr(rrule, '_freq'):
                # RRULE frequencies: YEARLY=0, MONTHLY=1, WEEKLY=2, DAILY=3, HOURLY=4, etc.
                # Allow YEARLY, MONTHLY, WEEKLY, and DAILY (0-3), but not more frequent
                if rrule._freq > 3:  # More frequent than daily (hourly, minutely, etc.)
                    raise ValidationError("Maximum recurrence frequency is daily. Sub-daily patterns (hourly, minutely) are not allowed.")

            return value

        except Exception as e:
            raise ValidationError(f"Invalid RRULE pattern: {str(e)}")


class RecurrenceWidget(forms.TextInput):
    """
    Widget for RRULE input with helpful placeholder and styling.
    """

    def __init__(self, attrs=None):
        default_attrs = {
            'placeholder': 'e.g., FREQ=DAILY;INTERVAL=2 (every 2 days)',
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)


class WaitingForForm(forms.Form):
    """
    Form for delegating items to someone else (transition to waiting_for).
    """
    person = forms.CharField(
        max_length=100,
        required=True,
        label="Who are you waiting for?",
        widget=forms.TextInput(attrs={
            'class': 'p-2 mt-1 focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md',
            'placeholder': 'Enter person or organization name'
        }),
        help_text="Person or organization you're delegating this to"
    )


class ItemForm(forms.ModelForm):
    estimated_duration = forms.ChoiceField(
        choices=[("", "Not specified")] + GTDDuration.choices,
        required=False,
        widget=forms.RadioSelect(),
    )
    energy = forms.ChoiceField(
        choices=[("", "None")] + GTDEnergy.choices,
        required=False,
        widget=forms.RadioSelect(),
    )

    # Reminder fields
    remind_at = forms.DateTimeField(
        required=False,
        widget=CustomDateTimeInput(),
        help_text='When to send the first reminder'
    )

    rrule = RecurrenceField(
        widget=RecurrenceWidget(),
        help_text='Recurrence pattern using RRULE format. Leave empty for one-time reminder.'
    )

    # Custom fields for autocomplete (to handle comma-separated values)
    contexts = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
        help_text='Comma-separated context IDs'
    )
    tags = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
        help_text='Comma-separated tag IDs'
    )

    class Meta:
        model = Item
        fields = [
            'title', 'description', 'priority', 'parent', 'area',
            'due_date', 'start_date', 'estimated_duration', 'energy', 'waiting_for_person',
            'remind_at', 'rrule', 'review_frequency_days', 'follow_up_date'
        ]
        widgets = {
            'title': forms.TextInput(),
            'description': forms.Textarea(attrs={'rows': 4}),
            'priority': forms.Select(),
            'parent': forms.Select(),
            'area': forms.Select(),
            'due_date': CustomDateInput(),
            'start_date': CustomDateInput(),
            'waiting_for_person': forms.TextInput(),
            'review_frequency_days': forms.NumberInput(attrs={'min': '1', 'max': '365'}),
            'follow_up_date': CustomDateInput(),
        }

    def __init__(self, item_flow: ItemFlow, user, *args, **kwargs):
        self.item_flow = item_flow
        super().__init__(*args, **kwargs)

        # parent relationship is only valid for projects/references
        current_status = self.instance.status if self.instance and self.instance.status else None
        if current_status not in GTDConfig.STATUS_WITH_PARENT_ALLOWED:
            current_status = GTDConfig.STATUS_WITH_PARENT_ALLOWED[0] if len(GTDConfig.STATUS_WITH_PARENT_ALLOWED) > 0 else None

        # set user-specific querysets
        if user:
            self.fields['parent'].queryset = Item.objects.filter(
                user=user,
                status=current_status,
                parent__pk=None,
            )
            self.fields['contexts'].queryset = Context.objects.filter(user=user)
            self.fields['area'].queryset = Area.objects.filter(user=user)
            self.fields['tags'].queryset = Tag.objects.filter(user=user)
        else:
            del self.fields['parent']
            # No user available, show empty querysets
            self.fields['contexts'].queryset = Context.objects.none()
            self.fields['area'].queryset = Area.objects.none()
            self.fields['tags'].queryset = Tag.objects.none()

        # Hide fields that don't apply to current status
        if not self.instance.is_waiting_for:
            del self.fields['waiting_for_person']
            del self.fields['follow_up_date']

        if not self.instance.is_someday_maybe:
            del self.fields['review_frequency_days']

        # For updates, adjust fields based on current status
        self._adjust_fields_for_status()

        # Initialize custom autocomplete fields with current values
        if self.instance and self.instance.pk:
            # Set initial values for tags (comma-separated IDs)
            tags_ids = list(self.instance.tags.values_list('id', flat=True))
            if tags_ids:
                self.fields['tags'].initial = ','.join(map(str, tags_ids))

            # Set initial values for contexts (comma-separated IDs)
            contexts_ids = list(self.instance.contexts.values_list('id', flat=True))
            if contexts_ids:
                self.fields['contexts'].initial = ','.join(map(str, contexts_ids))

    def _adjust_fields_for_status(self):
        """Adjust visible fields based on the item's current status"""
        current_status = self.instance.status if self.instance else None
        # Hide parent for project items to prevent circular references
        if current_status == GTDStatus.PROJECT:
            self.fields['parent'].widget = forms.HiddenInput()

    def clean_title(self):
        title = self.cleaned_data.get('title')
        if title and len(title.strip()) == 0:
            raise ValidationError("Title cannot be empty.")
        return title.strip() if title else title

    def get_initial_values_for_field(self, field_name):
        """Get initial values for autocomplete fields in format 'id1:text1,id2:text2'"""
        if not self.instance:
            return ""

        try:
            field_value = getattr(self.instance, field_name, None)
            if not field_value:
                return ""

            if field_name in ['tags', 'contexts']:  # Many-to-many fields
                items = field_value.all()
                if not items:
                    return ""
                return ",".join([f"{item.id}:{item.name}" for item in items])
            else:  # Single value fields like area, parent
                if hasattr(field_value, 'name'):
                    return f"{field_value.id}:{field_value.name}"
                elif hasattr(field_value, 'title'):
                    return f"{field_value.id}:{field_value.title}"
                else:
                    return f"{field_value.id}:{str(field_value)}"
        except Exception:
            # Log the error but don't break the form
            return ""

    def clean_parent(self):
        parent = self.cleaned_data.get('parent')
        if parent:
            # Check if parent is actually a project
            if parent.status not in GTDConfig.STATUS_WITH_PARENT_ALLOWED:
                raise ValidationError("Parent must be in " + ",".join(GTDConfig.STATUS_WITH_PARENT_ALLOWED))
        return parent

    def clean_contexts(self):
        contexts_value = self.cleaned_data.get('contexts')

        # Handle different input formats
        if isinstance(contexts_value, str) and contexts_value:
            try:
                # Handle comma-separated string: "1,2,3"
                ids = [int(id.strip()) for id in contexts_value.split(',') if id.strip().isdigit()]
                return Context.objects.filter(id__in=ids, user=self.instance.user if self.instance else None)
            except (ValueError, TypeError):
                return Context.objects.none()
        elif isinstance(contexts_value, list):
            try:
                # Handle list of IDs: [1, 2, 3] or ["1", "2", "3"]
                ids = [int(id) for id in contexts_value if str(id).isdigit()]
                return Context.objects.filter(id__in=ids, user=self.instance.user if self.instance else None)
            except (ValueError, TypeError):
                return Context.objects.none()

        return contexts_value

    def clean_tags(self):
        tags_value = self.cleaned_data.get('tags')

        # Handle different input formats
        if isinstance(tags_value, str) and tags_value:
            try:
                # Handle comma-separated string: "1,2,3"
                ids = [int(id.strip()) for id in tags_value.split(',') if id.strip().isdigit()]
                return Tag.objects.filter(id__in=ids, user=self.instance.user if self.instance else None)
            except (ValueError, TypeError):
                return Tag.objects.none()
        elif isinstance(tags_value, list):
            try:
                # Handle list of IDs: [1, 2, 3] or ["1", "2", "3"]
                ids = [int(id) for id in tags_value if str(id).isdigit()]
                return Tag.objects.filter(id__in=ids, user=self.instance.user if self.instance else None)
            except (ValueError, TypeError):
                return Tag.objects.none()

        return tags_value

    def clean(self):
        from django.utils import timezone
        cleaned_data = super().clean()
        priority = cleaned_data.get('priority')
        due_date = cleaned_data.get('due_date')
        remind_at = cleaned_data.get('remind_at')

        # Check if priority is URGENT and due_date is not set
        if priority == Priority.URGENT and not due_date:
            self.add_error('due_date', "Urgent items should have a due date")

        # Check if remind_at is in the past
        if remind_at and remind_at < timezone.now():
            self.add_error('remind_at', "Reminder date must be in the future")

        return cleaned_data

    def save(self, commit=True):
        item = super().save(commit=False)
        if commit:
            item.save()
            # Handle many-to-many relationships manually
            # Save tags
            tags_data = self.cleaned_data.get('tags')
            if tags_data:
                item.tags.set(tags_data)
            else:
                item.tags.clear()

            # Save contexts
            contexts_data = self.cleaned_data.get('contexts')
            if contexts_data:
                item.contexts.set(contexts_data)
            else:
                item.contexts.clear()
        return item
