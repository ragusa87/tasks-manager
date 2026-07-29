from django.conf import settings

from core.upload_types import accept_attribute, describe_types, recording_enabled

THEME_COOKIE_NAME = "theme"


def theme(request):
    """Theme override from the cookie: "light", "dark", or "" (follow the
    OS via color-scheme). Rendered as <html data-theme=...> so the choice
    applies on first paint, with no JS and no flash."""
    value = request.COOKIES.get(THEME_COOKIE_NAME, "")
    return {"THEME": value if value in ("light", "dark") else ""}


def site_settings(request):
    return {
        "MAX_FILE_SIZE_MB": settings.MAX_FILE_SIZE // (1024 * 1024),
        # Derived from ALLOWED_TYPES so labels/pickers follow the config.
        "ALLOWED_TYPES_LABEL": describe_types(settings.ALLOWED_TYPES),
        "ALLOWED_TYPES_ACCEPT": accept_attribute(settings.ALLOWED_TYPES),
        # The voice-note recorder uploads WAV; hidden when not allow-listed.
        "RECORDING_ENABLED": recording_enabled(settings.ALLOWED_TYPES),
    }
