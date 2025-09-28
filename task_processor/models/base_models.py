# gtd/models/base_models.py
from django.contrib.auth.models import User
from django.db import models

from task_processor.constants import GTDConfig
from task_processor.models.managers import AreaManager


class Context(models.Model):
    """
    GTD Contexts - Where or in what situation you can do tasks
    Examples: @home, @office, @phone, @computer, @errands
    """
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('name', 'user')
        ordering = ['name']
        indexes = [
            models.Index(fields=['user', 'name']),
        ]

    def __str__(self):
        return self.name


class Area(models.Model):
    """
    Areas of Responsibility - Ongoing areas of your life to maintain
    Examples: Health, Finance, Family, Career
    """
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = AreaManager()
    class Meta:
        unique_together = ('name', 'user')
        ordering = ['name']
        indexes = [
            models.Index(fields=['user', 'name']),
        ]

    def __str__(self):
        return self.name

    @classmethod
    def create_defaults_for_user(cls, user):
        """Create default areas for a new user"""
        for area_name in GTDConfig.DEFAULT_AREAS:
            cls.objects.get_or_create(
                name=area_name,
                user=user,
                defaults={'description': f'Default {area_name} area'}
            )


class Tag(models.Model):
    """
    Tags for Items - Flexible labeling system for categorization
    """
    name = models.CharField(max_length=50)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('name', 'user')
        ordering = ['name']
        indexes = [
            models.Index(fields=['user', 'name']),
        ]

    def __str__(self):
        return self.name