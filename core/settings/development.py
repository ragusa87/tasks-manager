"""
Development settings for core project.
"""

from .base import *  # noqa

# Use SQLite for development if PostgreSQL is not available
import os

DEBUG = True

# Re-read the remote-user header on every request (see base.py).
REMOTE_USER_FORCE_LOGOUT = True

ALLOWED_HOSTS = os.getenv(
    "ALLOWED_HOSTS", "localhost 127.0.0.1 tasks.docker.test"
).split()

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

# Redis cache, like production: cross-process flags (e.g. Nirvana import
# cancellation set by web, read by the Celery worker) need a shared backend —
# a per-process LocMemCache would leave the worker blind to them.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        # DB 2: the Channels layer lives in DB 1, and a cache.clear() must
        # not wipe channels state.
        "LOCATION": os.getenv("CACHE_URL", "redis://redis:6379/2"),
    }
}

# Override Vite settings for development
DJANGO_VITE["default"]["dev_mode"] = True
# Setup for traefik
DJANGO_VITE["default"]["dev_server_host"] = get_env_variable(
    "DJANGO_VITE_DEV_SERVER_HOST", "tasks-vite.docker.test"
)
DJANGO_VITE["default"]["dev_server_port"] = get_env_variable(
    "DJANGO_VITE_DEV_SERVER_PORT", "443"
)  # 5173
DJANGO_VITE["default"]["dev_server_protocol"] = get_env_variable(
    "DJANGO_VITE_DEV_SERVER_PROTOCOL", "https"
)
DJANGO_VITE["default"]["static_url_prefix"] = ""

SHOW_DJANGO_DEBUG_TOOLBAR = DEBUG
DEBUG_TOOLBAR_CONFIG = {
    "INTERCEPT_REDIRECTS": False,
    "SHOW_COLLAPSED": True,
    "SHOW_TOOLBAR_CALLBACK": lambda request: SHOW_DJANGO_DEBUG_TOOLBAR,
}
