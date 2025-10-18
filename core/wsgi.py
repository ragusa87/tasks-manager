"""
WSGI config for task_processing project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings.development")

application = get_wsgi_application()

# Wrap with WhiteNoise for static file serving in production
if os.environ.get("DJANGO_SETTINGS_MODULE") == "core.settings.production":
    from whitenoise import WhiteNoise

    application = WhiteNoise(application, root="/app/staticfiles")
    application.add_files("/app/staticfiles", prefix="static/")
