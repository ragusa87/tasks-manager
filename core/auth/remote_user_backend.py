from django.conf import settings
from django.contrib import auth
from django.contrib.auth import load_backend
from django.contrib.auth.backends import RemoteUserBackend
from django.contrib.auth.middleware import RemoteUserMiddleware


class AuthcrunchRemoteUserMiddleware(RemoteUserMiddleware):
    """
    Middleware that authenticates users based on a custom header set by proxy
    See https://docs.authcrunch.com/docs/authorize/headers#pass-jwt-token-claims-in-http-request-headers
    """

    header = "HTTP_X_TOKEN_USER_NAME"
    force_logout = settings.DEBUG

    def process_request(self, request):
        if request.user.is_authenticated and self.force_logout:
            self._force_logout(request)

        return super().process_request(request)

    def _force_logout(self, request):
        """
        Remove the current authenticated user in the request which is invalid
        but only if the user is authenticated via the RemoteUserBackend.
        """
        try:
            stored_backend = load_backend(
                request.session.get(auth.BACKEND_SESSION_KEY, "")
            )
        except ImportError:
            # backend failed to load
            auth.logout(request)
        else:
            if isinstance(stored_backend, RemoteUserBackend):
                auth.logout(request)


class AuthcrunchRemoteUserBackend(RemoteUserBackend):
    role_header = "HTTP_X_TOKEN_USER_ROLES"
    admin_role = "authp/admin"

    def configure_user(self, request, user, created=True):
        user = super().configure_user(request, user, created)

        user.is_staff = True
        user.is_active = True

        roles = request.META.get(self.role_header, "").split(" ")

        if self.admin_role in roles:
            user.is_superuser = True

        return user
