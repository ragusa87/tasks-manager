"""
Test settings for core project.
"""

from .base import *  # noqa

DEBUG = True

SECURE_PROXY_SSL_HEADER = None
SECURE_SSL_REDIRECT = False

# Pin upload/banner config so the suite is deterministic regardless of the host
# environment — a demo deployment may set ALLOW_FILES_UPLOAD=False / a banner,
# which would otherwise leak in through get_env_variable and break upload tests.
# Cases that need the disabled behaviour use @override_settings locally.
ALLOW_FILES_UPLOAD = True
INSTANCE_BANNER = ""
LOGIN_CAPTCHA_ENABLED = False
TURNSTILE_SITE_KEY = ""
TURNSTILE_SECRET_KEY = ""
# Pinned True so the conditionally-registered demo_login route (see
# task_processor/urls.py) exists during tests regardless of the host env.
IS_DEMO = True

# Use in-memory database for tests
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}


# Disable migrations during tests for faster execution
class DisableMigrations:
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


MIGRATION_MODULES = DisableMigrations()

# Use dummy cache for tests
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}

# Disable Celery during tests
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Email backend for tests
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Password hashers (faster for tests)
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Disable logging during tests
LOGGING_CONFIG = None
