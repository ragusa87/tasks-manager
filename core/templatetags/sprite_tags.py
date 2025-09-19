from django import template
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def sprite(sprite_name: str, sprite_size=24, **kwargs):
    class_name = "icon inline-block"
    if "class" in kwargs:
        class_name += " " + escape(str(kwargs.pop("class")))

    attrs_str = " ".join(
        f'{escape(key)}="{escape(value)}"' for key, value in kwargs.items()
    )
    return render_to_string(
        "partials/sprite.html",
        {
            "sprite_name": sprite_name,
            "sprite_size": int(sprite_size),
            "class_name": class_name,
            "attrs": mark_safe(attrs_str),
        },
    )


@register.simple_tag
def sprite_svg():
    import pathlib
    path = pathlib.Path(settings.BASE_DIR) / "templates" / "all-sprites.svg"
    with open(path, "r", encoding="utf-8") as f:
        return mark_safe(f.read())