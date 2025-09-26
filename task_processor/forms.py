from datetime import timedelta

from dateutil.rrule import rrulestr
from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError

from .constants import GTDEnergy, GTDStatus
from .models.base_models import Area, Context
from .models.item import Item, ItemFlow


class NativeDateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, *args, **kwargs):
        super().__init__(format=settings.DATE_INPUT_FORMAT, *args, **kwargs)

class NativeDateTimeInput(forms.DateInput):
    input_type = "datetime-local"

    def __init__(self, *args, **kwargs):
        super().__init__(format=settings.DATETIME_INPUT_FORMAT, *args, **kwargs)


class NativeDurationWidget(forms.MultiWidget):
    def __init__(self, attrs=None):
        hours_attrs = {'placeholder': 'Hours', 'min': '0', 'max': '999', 'step': '1'}
        minutes_attrs = {'placeholder': 'Minutes', 'min': '0', 'max': '59', 'step': '1'}

        if attrs:
            hours_attrs.update(attrs)
            minutes_attrs.update(attrs)

        widgets = [
            forms.NumberInput(attrs=hours_attrs),
            forms.NumberInput(attrs=minutes_attrs),
        ]
        super().__init__(widgets, attrs)

    def decompress(self, value):
        if value:
            if isinstance(value, timedelta):
                total_seconds = int(value.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                return [hours, minutes]
            elif isinstance(value, str):
                try:
                    # Try to parse HH:MM format
                    parts = value.split(':')
                    if len(parts) >= 2:
                        return [int(parts[0]), int(parts[1])]
                except (ValueError, IndexError):
                    pass
        return [None, None]

    def format_output(self, rendered_widgets):
        return '<div class="flex items-center space-x-2">{} <span class="text-sm text-gray-500">h</span> {} <span class="text-sm text-gray-500">min</span></div>'.format(
            rendered_widgets[0], rendered_widgets[1]
        )

    def value_from_datadict(self, data, files, name):
        hours = data.get(f'{name}_0', '')
        minutes = data.get(f'{name}_1', '')

        if hours == '' and minutes == '':
            return None

        try:
            hours = int(hours) if hours else 0
            minutes = int(minutes) if minutes else 0
            return timedelta(hours=hours, minutes=minutes)
        except (ValueError, TypeError):
            return None


class NativeDurationInput(forms.Field):
    widget = NativeDurationWidget

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        if value in self.empty_values:
            return None
        if isinstance(value, timedelta):
            return value
        return value

    def validate(self, value):
        super().validate(value)
        if value and isinstance(value, timedelta):
            if value.total_seconds() < 0:
                raise ValidationError("Duration cannot be negative.")
            if value.total_seconds() > 24 * 3600 * 999:  # Max 999 days
                raise ValidationError("Duration is too large.")


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
            'class': 'mt-1 focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)

class BaseItemForm(forms.ModelForm):
    estimated_duration = NativeDurationInput(required=False)
    energy = forms.ChoiceField(
        choices=[("", "----")] + GTDEnergy.choices,
        required=False,
        widget=forms.Select(attrs={
            'class': 'mt-1 block w-full py-2 px-3 border border-gray-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm'
        })
    )

    # Reminder fields
    remind_at = forms.DateTimeField(
        required=False,
        widget=NativeDateTimeInput(attrs={
            'class': 'mt-1 focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
        }),
        help_text='When to send the first reminder'
    )

    rrule = RecurrenceField(
        widget=RecurrenceWidget(),
        help_text='Recurrence pattern using RRULE format. Leave empty for one-time reminder.'
    )

    class Meta:
        model = Item
        fields = [
            'title', 'description', 'priority', 'parent_project', 'contexts', 'area',
            'due_date', 'start_date', 'estimated_duration', 'energy', 'waiting_for_person',
            'remind_at', 'rrule'
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'p-2 mt-1 focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md',
                'placeholder': 'Enter item title'
            }),
            'description': forms.Textarea(attrs={
                'class': 'p-2 mt-1 focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md',
                'rows': 4,
                'placeholder': 'Enter description'
            }),
            'priority': forms.Select(attrs={
                'class': 'mt-1 block w-full py-2 px-3 border border-gray-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm'
            }),
            'parent_project': forms.Select(attrs={
                'class': 'mt-1 block w-full py-2 px-3 border border-gray-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm'
            }),
            'contexts': forms.SelectMultiple(attrs={
                'class': 'mt-1 block w-full py-2 px-3 border border-gray-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm',
                'size': '4'
            }),
            'area': forms.Select(attrs={
                'class': 'mt-1 block w-full py-2 px-3 border border-gray-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm'
            }),
            'due_date': NativeDateInput(attrs={
                'class': 'mt-1 focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md',
            }),
            'start_date': NativeDateInput(attrs={
                'class': 'mt-1 focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md',
            }),
            'waiting_for_person': forms.TextInput(attrs={
                'class': 'p-2 mt-1 focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md',
                'placeholder': 'Bob and Alice'
            }),
        }

    def __init__(self, item_flow: ItemFlow, user, *args, **kwargs):
        self.item_flow = item_flow
        super().__init__(*args, **kwargs)

        # Apply styling to duration widget
        duration_widget_attrs = {
            'class': 'focus:ring-blue-500 focus:border-blue-500 w-16 shadow-sm sm:text-sm border-gray-300 rounded-md text-center'
        }
        self.fields['estimated_duration'].widget = NativeDurationWidget(attrs=duration_widget_attrs)

        # Set user-specific querysets
        if user:
            self.fields['parent_project'].queryset = Item.objects.filter(
                user=user,
                status='project',
                parent_project__pk=None,
            )
            self.fields['contexts'].queryset = Context.objects.filter(user=user)
            self.fields['area'].queryset = Area.objects.filter(user=user)
        else:
            del self.fields['parent_project']
            # No user available, show empty querysets
            self.fields['contexts'].queryset = Context.objects.none()
            self.fields['area'].queryset = Area.objects.none()

        if not self.instance.is_waiting_for:
            del self.fields['waiting_for_person']

    def clean_title(self):
        title = self.cleaned_data.get('title')
        if title and len(title.strip()) == 0:
            raise ValidationError("Title cannot be empty or just whitespace.")
        return title.strip() if title else title

    def clean_parent_project(self):
        parent_project = self.cleaned_data.get('parent_project')
        if parent_project:
            # Check if parent is actually a project
            if parent_project.status != 'project':
                raise ValidationError("Parent must be a project.")

        return parent_project





class ItemCreateForm(BaseItemForm):
    def __init__(self, item_flow: ItemFlow, user, *args, **kwargs):
        super().__init__(item_flow, user, *args, **kwargs)
        self.fields['title'].required = True

    def save(self, commit=True):
        item = super().save(commit=False)
        if commit:
            item.save()
        return item


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


class ItemDetailForm(forms.ModelForm):
    def __init__(self, item_flow: ItemFlow, user, *args, **kwargs):
        self.item_flow = item_flow
        self.user = user
        super().__init__(*args, **kwargs)

    class Meta:
        model = Item
        fields = [
            'title', 'description'
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'p-2 mt-1 focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md',
                'placeholder': 'Enter item title'
            }),
            'description': forms.Textarea(attrs={
                'class': 'p-2 mt-1 focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md',
                'rows': 4,
                'placeholder': 'Enter description'
            }),
        }
class ItemUpdateProjectForm(ItemDetailForm):
    pass

class ItemUpdateForm(BaseItemForm):
    def __init__(self, item_flow: ItemFlow, user, *args, **kwargs):
        super().__init__(item_flow, user, *args, **kwargs)

        # For updates, adjust fields based on current status
        self._adjust_fields_for_status()

    def _adjust_fields_for_status(self):
        """Adjust visible fields based on the item's current status"""
        current_status = self.instance.status if self.instance else None
        # Hide parent_project for project items to prevent circular references
        if current_status == GTDStatus.PROJECT:
            self.fields['parent_project'].widget = forms.HiddenInput()

    def save(self, commit=True):
        item = super().save(commit=False)
        if commit:
            item.save()
        return item