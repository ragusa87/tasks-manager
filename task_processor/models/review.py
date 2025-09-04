# gtd/models/review.py
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from task_processor.constants import GTDConfig, ReviewType


class Review(models.Model):
    """
    GTD Weekly/Monthly Reviews tracking
    """
    review_type = models.CharField(max_length=20, choices=ReviewType.choices)
    review_date = models.DateField(default=timezone.now)
    notes = models.TextField(blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    # Metrics captured during review
    inbox_items_processed = models.IntegerField(default=0)
    projects_reviewed = models.IntegerField(default=0)
    next_actions_identified = models.IntegerField(default=0)
    someday_maybe_reviewed = models.IntegerField(default=0)
    waiting_for_followed_up = models.IntegerField(default=0)

    class Meta:
        ordering = ['-review_date']
        unique_together = ('user', 'review_type', 'review_date')
        indexes = [
            models.Index(fields=['user', 'review_type']),
            models.Index(fields=['review_date']),
        ]

    def __str__(self):
        return f"{self.get_review_type_display()} - {self.review_date}"

    @classmethod
    def get_latest_review(cls, user, review_type):
        """Get the most recent review of specified type for user"""
        return cls.objects.filter(
            user=user,
            review_type=review_type
        ).first()

    @classmethod
    def is_review_due(cls, user, review_type):
        """Check if a review is due based on type frequency"""
        latest_review = cls.get_latest_review(user, review_type)
        if not latest_review:
            return True

        days_since_last = (timezone.now().date() - latest_review.review_date).days
        return days_since_last >= GTDConfig.REVIEW_INTERVALS.get(review_type, 7)

    @classmethod
    def get_review_summary(cls, user, review_type=None, days=30):
        """Get summary of reviews for a user"""
        queryset = cls.objects.filter(user=user)

        if review_type:
            queryset = queryset.filter(review_type=review_type)

        if days:
            since_date = timezone.now().date() - timezone.timedelta(days=days)
            queryset = queryset.filter(review_date__gte=since_date)

        return queryset.aggregate(
            total_reviews=models.Count('id'),
            total_inbox_processed=models.Sum('inbox_items_processed'),
            total_projects_reviewed=models.Sum('projects_reviewed'),
            total_next_actions=models.Sum('next_actions_identified'),
            avg_inbox_per_review=models.Avg('inbox_items_processed'),
        )


class ItemStateLog(models.Model):
    """
    Log of all state transitions for audit trail
    Automatically created by django-fsm-log
    """
    item = models.ForeignKey('Item', on_delete=models.CASCADE, related_name='state_logs')
    from_state = models.CharField(max_length=20)
    to_state = models.CharField(max_length=20)
    transition = models.CharField(max_length=50)
    by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['item', 'timestamp']),
            models.Index(fields=['by', 'timestamp']),
            models.Index(fields=['transition']),
        ]

    def __str__(self):
        return f"{self.item.title}: {self.from_state} → {self.to_state}"

    @classmethod
    def get_user_activity(cls, user, days=7):
        """Get recent state transition activity for a user"""
        since_date = timezone.now() - timezone.timedelta(days=days)
        return cls.objects.filter(
            by=user,
            timestamp__gte=since_date
        ).select_related('item')

    @classmethod
    def get_transition_stats(cls, user, days=30):
        """Get statistics about state transitions"""
        since_date = timezone.now() - timezone.timedelta(days=days)
        return cls.objects.filter(
            by=user,
            timestamp__gte=since_date
        ).values('transition').annotate(
            count=models.Count('id')
        ).order_by('-count')