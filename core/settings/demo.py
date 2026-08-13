"""
Demo settings: a locked-down, self-resetting public instance.

Builds on the production settings (security headers, WhiteNoise, DEBUG off) but:
  * enforces demo mode and disables file uploads regardless of the environment,
  * runs on a standalone SQLite database, so no Postgres container is needed,
  * ships a default instance banner that operators can still override via the
    INSTANCE_BANNER environment variable.

Select it with DJANGO_SETTINGS_MODULE=core.settings.demo.
"""

from core.settings import get_env_variable

from .production import *  # noqa

# Enforced regardless of the environment — this is what makes it "the demo".
IS_DEMO = True
ALLOW_FILES_UPLOAD = False

# Standalone SQLite so the demo needs no Postgres container. Defaults to a fixed
# path on its own `data` volume (mounted at /app/data by
# docker-compose.override.demo-example.yaml), kept off the media volume which
# stays empty while uploads are disabled. Override the path with SQLITE_DB_PATH.
# `fixturize --clear` supports SQLite, so the periodic reset works.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": get_env_variable(
            "SQLITE_DB_PATH", str(BASE_DIR / "data" / "db.sqlite3")
        ),
    }
}

# Demo-appropriate default; still overridable with the INSTANCE_BANNER env var.
INSTANCE_BANNER = get_env_variable(
    "INSTANCE_BANNER",
    "Public demo — file uploads are disabled and all data resets periodically.",
)
