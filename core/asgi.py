"""
ASGI config for task_processing project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

import task_processor.routing

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings.development")

application = ProtocolTypeRouter(
    {
        "http": get_asgi_application(),
        "websocket": AuthMiddlewareStack(
            URLRouter(task_processor.routing.websocket_urlpatterns)
        ),
    }
)
