"""Server-side handling of user-authored Markdown (e.g. ``Item.description``).

The description is stored as Markdown limited to a small subset — bold,
italic, strikethrough, links and bullet/ordered lists. It is authored
client-side with a Milkdown editor, but the client is never a trust boundary,
so everything is re-checked here before it reaches the database.

Both helpers are pure functions with no Django/global dependencies so they can
be unit-tested in isolation:

- :func:`sanitize_markdown` renders Markdown to HTML, strips anything outside
  the allowed inline set with ``nh3`` (drops scripts, block elements, event
  handlers and unsafe link schemes), then converts the safe HTML back to
  Markdown so the field stays Markdown.
- :func:`strip_markdown` flattens Markdown to plain text for list/preview
  display where formatting would only be noise.
"""

from __future__ import annotations

import html
import re

import markdown as markdown_lib
import nh3
from markdownify import markdownify

# Allow-list: inline formatting plus bullet/ordered lists. No headings,
# tables, code blocks, images or raw HTML survive. ``b``/``i`` are accepted on
# input (some clients emit them) but markdownify normalises everything to
# ``**``/``*``/``~~``/``[]()`` and ``-``/``1.`` list markers.
ALLOWED_TAGS = {"p", "br", "strong", "em", "b", "i", "del", "s", "a", "ul", "ol", "li"}
ALLOWED_ATTRIBUTES = {"a": {"href", "title"}}
ALLOWED_URL_SCHEMES = {"http", "https", "mailto"}


# A single render/clean/convert pass is not idempotent: markdownify unescapes
# HTML entities, so e.g. ``&lt;script&gt;`` comes back as a raw ``<script>``
# tag that only the *next* pass would strip. Iterating to a fixed point closes
# that hole — a string equal to its own sanitisation cannot contain any markup
# nh3 would reject, encoded or not.
_MAX_SANITIZE_PASSES = 10


def sanitize_markdown(text: str | None) -> str:
    """Return ``text`` reduced to the allowed inline Markdown subset.

    The result is a fixed point of the sanitisation pass, so it is idempotent
    and free of raw or entity-encoded HTML outside the allow-list.
    """
    if not text or not text.strip():
        return ""

    result = text
    for _ in range(_MAX_SANITIZE_PASSES):
        cleaned = _sanitize_once(result)
        if cleaned == result:
            return cleaned
        result = cleaned
    # No fixed point within the cap (adversarial nesting): degrade to plain
    # text rather than store something that would keep mutating on save.
    return strip_markdown(result)


def _sanitize_once(text: str) -> str:
    dirty_html = markdown_lib.markdown(text)
    safe_html = nh3.clean(
        dirty_html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_URL_SCHEMES,
        link_rel=None,
    )
    # markdownify keeps GFM-style delimiters (**bold**, *italic*, ~~strike~~)
    # and uses "-" for every bullet-list level.
    result = markdownify(safe_html, strong_em_symbol="*", bullets="-").strip()
    # Collapse the blank lines markdownify inserts between paragraphs so the
    # stored value stays compact and stable across repeated sanitising.
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result


def strip_markdown(text: str | None) -> str:
    """Return ``text`` as a single line of plain text (formatting removed)."""
    if not text or not text.strip():
        return ""

    rendered_html = markdown_lib.markdown(text)
    plain = nh3.clean(rendered_html, tags=set(), attributes={})
    plain = html.unescape(plain)
    return re.sub(r"\s+", " ", plain).strip()
