from django.conf import settings

from core.upload_types import accept_attribute, describe_types


def site_settings(request):
    return {
        "MAX_FILE_SIZE_MB": settings.MAX_FILE_SIZE // (1024 * 1024),
        # Derived from ALLOWED_TYPES so labels/pickers follow the config.
        "ALLOWED_TYPES_LABEL": describe_types(settings.ALLOWED_TYPES),
        "ALLOWED_TYPES_ACCEPT": accept_attribute(settings.ALLOWED_TYPES),
    }
