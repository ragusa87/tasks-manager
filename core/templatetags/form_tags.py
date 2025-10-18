from django import template
from django.forms import BoundField

register = template.Library()


@register.filter(name="attr")
def attr(field, css):
    """
    Add or update attributes on a form field.

    Usage: {{ form.field|attr:"class:form-control,placeholder:Enter text" }}

    Supports:
    - class: CSS classes (will be merged with existing classes)
    - Any other HTML attribute

    Examples:
    {{ form.email|attr:"class:form-control,placeholder:Enter email" }}
    {{ form.field|attr:"class:custom-class" }}
    """
    if not isinstance(field, BoundField):
        return field

    attrs = {}

    # Parse the css string
    if css:
        pairs = [pair.strip() for pair in css.split(",")]
        for pair in pairs:
            if ":" in pair:
                key, value = pair.split(":", 1)
                key = key.strip()
                value = value.strip()

                # Special handling for class attribute
                if key == "class":
                    # Merge with existing classes
                    existing_class = field.field.widget.attrs.get("class", "")
                    if existing_class:
                        attrs["class"] = f"{existing_class} {value}"
                    else:
                        attrs["class"] = value
                else:
                    attrs[key] = value

    return field.as_widget(attrs=attrs)
