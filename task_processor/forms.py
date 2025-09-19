from django import forms
from django.core.exceptions import ValidationError

from .models.base_models import Area, Context
from .models.item import Item, ItemFlow


class BaseItemForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = [
            'title', 'description', 'priority', 'parent_project', 'contexts', 'area',
            'due_date', 'start_date', 'estimated_duration'
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
            'due_date': forms.DateTimeInput(attrs={
                'class': 'mt-1 focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md',
                'type': 'datetime-local'
            }),
            'start_date': forms.DateTimeInput(attrs={
                'class': 'mt-1 focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md',
                'type': 'datetime-local'
            }),
            'estimated_duration': forms.TimeInput(attrs={
                'class': 'mt-1 focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md',
                'type': 'time'
            }),
        }

    def __init__(self, item_flow: ItemFlow, user, *args, **kwargs):
        self.item_flow = item_flow
        super().__init__(*args, **kwargs)

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


class ItemUpdateForm(BaseItemForm):
    def __init__(self, item_flow: ItemFlow, user, *args, **kwargs):
        super().__init__(item_flow, user, *args, **kwargs)

        # For updates, adjust fields based on current status
        self._adjust_fields_for_status()

    def _adjust_fields_for_status(self):
        """Adjust visible fields based on the item's current status"""
        current_status = self.item_flow.item.status

        # Hide parent_project for project items to prevent circular references
        if current_status == 'project':
            self.fields['parent_project'].widget = forms.HiddenInput()

    def save(self, commit=True):
        item = super().save(commit=False)
        if commit:
            item.save()
        return item