"""Human-facing derivations of the upload MIME allow-list.

``settings.ALLOWED_TYPES`` is the single source of truth for which files may
be attached; these helpers derive the UI strings from it so labels and file
pickers never drift from the actual validation:

- :func:`describe_types` -> "PDF, image or audio" (dropzone label, error text)
- :func:`accept_attribute` -> ".pdf,application/pdf,image/*,audio/*,.m4a"
  (the <input type="file" accept> attribute)
- :func:`recording_enabled` -> whether the voice-note recorder can upload
  (it always encodes WAV; see frontend/js/audio-recorder.js)

Pure functions, no Django dependency.
"""

from __future__ import annotations

# python-magic identifies audio recordings by their container, not their
# codec: m4a is reported as video/mp4 and audio-only webm as video/webm.
# When audio is allowed these entries are container quirks, not a video
# category of their own, and only warrant a file-picker extension hint.
_AUDIO_CONTAINER_ALIASES = {
    "video/mp4": ".m4a",
    "video/webm": ".webm",
}


def _is_audio_container_alias(mime: str, allowed_types: list[str]) -> bool:
    return mime in _AUDIO_CONTAINER_ALIASES and any(
        t.startswith("audio/") for t in allowed_types
    )


def type_categories(allowed_types: list[str]) -> list[str]:
    """Ordered, deduplicated category names for a MIME allow-list."""
    categories: list[str] = []

    def add(category: str) -> None:
        if category not in categories:
            categories.append(category)

    for mime in allowed_types:
        if mime == "application/pdf":
            add("PDF")
        elif mime.startswith("image/"):
            add("image")
        elif mime.startswith("audio/"):
            add("audio")
        elif _is_audio_container_alias(mime, allowed_types):
            pass
        elif mime.startswith("video/"):
            add("video")
        elif mime.startswith("text/"):
            add("text")
        else:
            add("file")
    return categories


def describe_types(allowed_types: list[str]) -> str:
    """Human list of allowed categories, e.g. "PDF, image or audio"."""
    categories = type_categories(allowed_types)
    if not categories:
        return "file"
    if len(categories) == 1:
        return categories[0]
    return ", ".join(categories[:-1]) + " or " + categories[-1]


def accept_attribute(allowed_types: list[str]) -> str:
    """Value for <input type="file" accept="..."> matching the allow-list."""
    parts: list[str] = []

    def add(part: str) -> None:
        if part not in parts:
            parts.append(part)

    for mime in allowed_types:
        if mime == "application/pdf":
            add(".pdf")
            add("application/pdf")
        elif mime.startswith("image/"):
            add("image/*")
        elif mime.startswith("audio/"):
            add("audio/*")
            if mime in ("audio/mp4", "audio/x-m4a"):
                add(".m4a")
        elif _is_audio_container_alias(mime, allowed_types):
            add(_AUDIO_CONTAINER_ALIASES[mime])
        else:
            add(mime)
    return ",".join(parts)


def recording_enabled(allowed_types: list[str]) -> bool:
    """Whether the voice-note recorder can upload under this allow-list.

    The recorder always encodes 16-bit PCM WAV, which python-magic detects
    as audio/x-wav — that exact entry must be allow-listed or the upload
    would be rejected; the template hides the recorder otherwise.
    """
    return "audio/x-wav" in allowed_types
