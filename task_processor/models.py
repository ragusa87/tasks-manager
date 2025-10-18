"""
Models - Main models file for Django auto-discovery

This file imports all models from the models package so Django can find them.
The actual model definitions are organized in separate files within the models/ package.
"""

# Import all models so Django can discover them
from .constants import GTDConfig, GTDStatus, Priority, ReviewType
from .models.base_models import Area, Context, Tag
from .models.item import Item
from .models.review import ItemStateLog, Review

# Make sure Django can find all models
__all__ = [
    # Constants and Enums
    "GTDStatus",
    "Priority",
    "ReviewType",
    "GTDConfig",
    # Models
    "Context",
    "Area",
    "Tag",
    "Item",
    "Review",
    "ItemStateLog",
]
