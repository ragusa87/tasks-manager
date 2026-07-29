from ninja import NinjaAPI

from task_processor.api.auth import ApiKeyAuth
from task_processor.api.documents import router as documents_router
from task_processor.api.items import router as items_router
from task_processor.api.taxonomies import router as taxonomies_router

api = NinjaAPI(
    title="Tasks Manager API",
    version="1.0.0",
    auth=ApiKeyAuth(),
    urls_namespace="api",
)
api.add_router("/items", items_router)
api.add_router("", taxonomies_router)
api.add_router("", documents_router)
