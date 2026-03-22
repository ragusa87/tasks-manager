from django.conf import settings


def site_settings(request):
    return {
        "MAX_FILE_SIZE_MB": settings.MAX_FILE_SIZE // (1024 * 1024),
    }
