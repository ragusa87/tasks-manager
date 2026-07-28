from django import template

from task_processor.markdown_utils import strip_markdown as _strip_markdown

register = template.Library()


@register.filter(name="strip_markdown")
def strip_markdown(value):
    """Flatten Markdown to a single line of plain text for list/preview display.

    Usage: {{ item.description|strip_markdown|truncatechars:120 }}
    """
    return _strip_markdown(value)
