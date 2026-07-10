from datetime import datetime

from django.utils import timezone
from ninja import Field, ModelSchema, Schema
from pydantic import field_validator, model_validator

from task_processor.constants import GTDDuration, GTDEnergy, GTDStatus, Priority
from task_processor.models import Area, Context, Item, Tag

# Creating an already-dead item makes no sense (and Item.save() would fight it)
CREATABLE_STATUSES = [
    status
    for status in GTDStatus
    if status not in (GTDStatus.COMPLETED, GTDStatus.CANCELLED)
]


def _ensure_aware(value: datetime | None) -> datetime | None:
    if value is not None and timezone.is_naive(value):
        return timezone.make_aware(value)
    return value


class TagOut(ModelSchema):
    class Meta:
        model = Tag
        fields = ["id", "name"]


class ContextOut(ModelSchema):
    class Meta:
        model = Context
        fields = ["id", "name", "description"]


class AreaOut(ModelSchema):
    class Meta:
        model = Area
        fields = ["id", "name", "description"]


class TagIn(Schema):
    name: str = Field(min_length=1, max_length=50)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Name cannot be blank")
        return value


class NamedIn(TagIn):
    """Input for contexts and areas: a name plus an optional description."""

    name: str = Field(min_length=1, max_length=100)
    description: str = ""


class ItemIn(Schema):
    title: str = Field(min_length=1, max_length=1024)
    description: str = ""
    status: GTDStatus = GTDStatus.INBOX
    priority: Priority = Priority.NORMAL
    energy: GTDEnergy | None = None
    estimated_duration: GTDDuration | None = None
    due_date: datetime | None = None
    start_date: datetime | None = None
    remind_at: datetime | None = None
    parent_id: int | None = None
    area_id: int | None = None
    context_ids: list[int] = []
    tag_ids: list[int] = []

    @field_validator("title")
    @classmethod
    def strip_title(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Title cannot be empty")
        return value

    @field_validator("status")
    @classmethod
    def creatable_status(cls, value):
        if value not in CREATABLE_STATUSES:
            allowed = ", ".join(status.value for status in CREATABLE_STATUSES)
            raise ValueError(f"Status must be one of: {allowed}")
        return value

    @field_validator("due_date", "start_date", "remind_at")
    @classmethod
    def make_aware(cls, value):
        return _ensure_aware(value)

    @model_validator(mode="after")
    def business_rules(self):
        # Mirrors ItemForm.clean()
        if self.priority == Priority.URGENT and self.due_date is None:
            raise ValueError("Urgent items must have a due date")
        if self.remind_at and self.remind_at < timezone.now():
            raise ValueError("Reminder date must be in the future")
        return self


class ItemOut(ModelSchema):
    tags: list[TagOut]
    contexts: list[ContextOut]
    area: AreaOut | None = None

    class Meta:
        model = Item
        fields = [
            "id",
            "title",
            "description",
            "status",
            "priority",
            "energy",
            "estimated_duration",
            "due_date",
            "start_date",
            "remind_at",
            "parent",
            "is_completed",
            "created_at",
            "updated_at",
        ]
