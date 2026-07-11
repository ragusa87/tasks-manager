from ninja.security import HttpBearer

from task_processor.models import ApiKey


class ApiKeyAuth(HttpBearer):
    """Authenticates requests via 'Authorization: Bearer <api-key>'."""

    def authenticate(self, request, token):
        api_key = ApiKey.authenticate(token) if token else None
        if api_key is None:
            return None  # ninja responds with 401
        # Existing user-scoping idioms (Item.objects.for_user(request.user)) keep working
        request.user = api_key.user
        return api_key
