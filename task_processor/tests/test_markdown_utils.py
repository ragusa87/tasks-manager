"""Unit tests for the Markdown sanitizer/stripper (pure functions, no DB)."""

import pytest
from django.contrib.auth.models import User
from django.test import TestCase

from task_processor.api.items import create_item
from task_processor.api.schemas import ItemIn
from task_processor.markdown_utils import sanitize_markdown, strip_markdown
from task_processor.models import Item


class TestSanitizeMarkdown:
    @pytest.mark.parametrize("value", ["", "   ", None])
    def test_empty_is_empty(self, value):
        assert sanitize_markdown(value) == ""

    def test_keeps_bold(self):
        assert sanitize_markdown("**bold**") == "**bold**"

    def test_keeps_italic(self):
        assert sanitize_markdown("*italic*") == "*italic*"

    def test_keeps_strikethrough(self):
        assert "~~gone~~" in sanitize_markdown("~~gone~~")

    def test_keeps_safe_link(self):
        result = sanitize_markdown("[liip](https://liip.ch)")
        assert result == "[liip](https://liip.ch)"

    def test_keeps_mailto_link(self):
        result = sanitize_markdown("[mail](mailto:a@b.ch)")
        assert "mailto:a@b.ch" in result

    def test_plain_text_passthrough(self):
        assert sanitize_markdown("just some text") == "just some text"

    def test_keeps_autolink(self):
        assert sanitize_markdown("<https://example.com>") == "<https://example.com>"

    def test_bare_url_preserved(self):
        # remarkGFM autolinks bare URLs client-side; the server keeps them intact.
        assert sanitize_markdown("https://example.com") == "https://example.com"

    # --- security ---------------------------------------------------------
    def test_strips_script_tag(self):
        result = sanitize_markdown("hello <script>alert(1)</script> world")
        assert "script" not in result.lower()
        assert "alert" not in result

    def test_strips_javascript_link_scheme(self):
        result = sanitize_markdown("[x](javascript:alert(1))")
        assert "javascript" not in result.lower()

    def test_strips_event_handler_html(self):
        result = sanitize_markdown('<img src=x onerror="alert(1)">')
        assert "onerror" not in result.lower()
        assert "<img" not in result.lower()

    def test_strips_data_uri_link(self):
        result = sanitize_markdown("[x](data:text/html;base64,PHNjcmlwdD4=)")
        assert "data:" not in result.lower()

    # --- block elements are flattened to inline/plain ---------------------
    def test_heading_downgraded(self):
        result = sanitize_markdown("# Heading")
        assert "#" not in result
        assert "Heading" in result

    def test_keeps_bullet_list(self):
        result = sanitize_markdown("- one\n- two")
        assert result == "- one\n- two"

    def test_keeps_ordered_list(self):
        result = sanitize_markdown("1. one\n2. two")
        assert result == "1. one\n2. two"

    def test_code_block_flattened(self):
        result = sanitize_markdown("```python\nprint(1)\n```")
        assert "```" not in result

    def test_image_removed(self):
        result = sanitize_markdown("![alt](https://x/y.png)")
        assert "![" not in result

    # --- idempotency ------------------------------------------------------
    @pytest.mark.parametrize(
        "value",
        [
            "**bold** and *italic*",
            "[liip](https://liip.ch)",
            "~~strike~~ text",
            "# heading\n\n- a\n- b",
            "plain paragraph one\n\nparagraph two",
            "- one\n- two\n- three",
            "1. first\n2. second",
            "<https://example.com>",
        ],
    )
    def test_idempotent(self, value):
        once = sanitize_markdown(value)
        twice = sanitize_markdown(once)
        assert once == twice


class TestStripMarkdown:
    @pytest.mark.parametrize("value", ["", "   ", None])
    def test_empty(self, value):
        assert strip_markdown(value) == ""

    def test_removes_formatting(self):
        assert strip_markdown("**bold** and *italic*") == "bold and italic"

    def test_link_becomes_text(self):
        assert strip_markdown("[liip](https://liip.ch)") == "liip"

    def test_collapses_whitespace_and_newlines(self):
        assert strip_markdown("line one\n\nline two") == "line one line two"

    def test_unescapes_entities(self):
        assert strip_markdown("a & b") == "a & b"


class TestDescriptionSanitizedOnSave(TestCase):
    """The model is the chokepoint, so every write path (web form, admin,
    shell and the Ninja API) inherits sanitization via Item.save()."""

    def setUp(self):
        self.user = User.objects.create_user(username="md", password="x")

    def test_model_save_sanitizes(self):
        item = Item.objects.create(
            title="t",
            user=self.user,
            description="**ok** <script>alert(1)</script> [x](javascript:1)",
        )
        item.refresh_from_db()
        assert "<script" not in item.description.lower()
        assert "javascript" not in item.description.lower()
        assert "**ok**" in item.description

    def test_api_create_sanitizes(self):
        item = create_item(
            self.user,
            ItemIn(title="t", description="# H\n\n<script>x</script> **b**"),
        )
        item.refresh_from_db()
        assert "<script" not in item.description.lower()
        assert "#" not in item.description
        assert "**b**" in item.description
