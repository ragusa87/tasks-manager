"""
Development settings for core project.
"""

from .base import * # noqa
# Use SQLite for development if PostgreSQL is not available
import os

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "tasks.docker.test"]

# Add debug toolbar for development
INSTALLED_APPS += ["debug_toolbar"]

MIDDLEWARE = [
    "debug_toolbar.middleware.DebugToolbarMiddleware",
] + MIDDLEWARE

# Debug toolbar configuration
INTERNAL_IPS = [
    "127.0.0.1",
]



if not os.getenv("DB_NAME"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# Email backend for development
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Disable caching in development
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}

# Override Vite settings for development
DJANGO_VITE["default"]["dev_mode"] = True
# Setup for traefik
DJANGO_VITE["default"]["dev_server_host"] = get_env_variable("DJANGO_VITE_DEV_SERVER_HOST", "tasks-vite.docker.test")
DJANGO_VITE["default"]["dev_server_port"] = get_env_variable("DJANGO_VITE_DEV_SERVER_PORT", "443") # 5173
DJANGO_VITE["default"]["dev_server_protocol"] = get_env_variable("DJANGO_VITE_DEV_SERVER_PROTOCOL", "https")
DJANGO_VITE["default"]["static_url_prefix"] = "frontend/js/"
