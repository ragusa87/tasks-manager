from ninja import NinjaAPI
from ninja.security import django_auth

from task_processor.api.auth import ApiKeyAuth
from task_processor.api.documents import router as documents_router
from task_processor.api.items import router as items_router
from task_processor.api.taxonomies import router as taxonomies_router

api = NinjaAPI(
    title="Tasks Manager API",
    version="1.0.0",
    # Order matters: HttpBearer returns None when the Authorization header is
    # absent, so browser requests fall through to django_auth (session cookie
    # + CSRF). django_auth raises 403 on CSRF failure, so it must come last
    # or it would block bearer clients that send no CSRF token.
    auth=[ApiKeyAuth(), django_auth],
    urls_namespace="api",
)
api.add_router("/items", items_router)
api.add_router("", taxonomies_router)
api.add_router("", documents_router)
