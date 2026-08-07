from django.conf import settings
from django.contrib import auth
from django.contrib.auth import load_backend
from django.contrib.auth.backends import RemoteUserBackend
from django.contrib.auth.middleware import PersistentRemoteUserMiddleware

from core.auth.jwt import client_roles, decode_jwt_claims


class AuthcrunchRemoteUserMiddleware(PersistentRemoteUserMiddleware):
    """
    Middleware that authenticates users based on a custom header set by proxy
    See https://docs.authcrunch.com/docs/authorize/headers#pass-jwt-token-claims-in-http-request-headers

    Persistent variant: the reverse proxy does not set the header on /api/*
    routes (they are open to bearer-key clients), so the plain
    RemoteUserMiddleware would log the user out — flushing the session and,
    on the re-login that follows, rotating the CSRF secret under every open
    page — each time the browser calls the API with its session cookie.
    """

    header = "HTTP_X_TOKEN_USER_NAME"

    @property
    def force_logout(self):
        return settings.REMOTE_USER_FORCE_LOGOUT

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


class TraefikKeycloakRemoteUserMiddleware(AuthcrunchRemoteUserMiddleware):
    """
    Remote-user middleware for the traefik keycloakopenid plugin.

    Authenticates the user from the same ``X-Token-User-Name`` header as its
    parent, then maps Django ``is_staff`` / ``is_superuser`` from the OAuth
    client's roles carried in the auth-proxy JWT (the ``AUTH_TOKEN`` cookie).

    Roles are taken from ``resource_access.<AUTH_PROXY_OAUTH_CLIENT>.roles`` —
    the roles assigned to this specific application's user, not the user's
    global realm roles. ``AUTH_PROXY_SUPERUSER_ROLES`` maps to ``is_superuser``
    and ``AUTH_PROXY_STAFF_ROLES`` (plus every superuser) to ``is_staff``.

    Role sync runs only when the trusted header is present on the request. On
    /api/* routes the proxy sets no header (yet the browser still sends the
    cookie), so we must not read roles from a cookie the proxy did not gate —
    the stored flags from the last real page request are kept instead.
    """

    def process_request(self, request):
        super().process_request(request)

        if self.header in request.META and request.user.is_authenticated:
            self._sync_roles(request)

    def _sync_roles(self, request):
        user = request.user

        # Keycloak is the source of truth for these flags: they are recomputed
        # from the token's roles on every gated request, so a grant made
        # manually via the Django admin is overwritten on the user's next page
        # load. An absent or non-JWT cookie yields an empty role set, which
        # intentionally *demotes* the user: a role revoked in Keycloak must take
        # effect on the next gated page request, not linger until logout. In the
        # documented deployment the proxy always forwards a fresh cookie together
        # with the header, so this only ever reflects a genuine role change.
        roles = client_roles(
            decode_jwt_claims(request.COOKIES.get(settings.AUTH_PROXY_COOKIE_NAME, "")),
            settings.AUTH_PROXY_OAUTH_CLIENT,
        )
        is_superuser = bool(roles & set(settings.AUTH_PROXY_SUPERUSER_ROLES))
        is_staff = is_superuser or bool(roles & set(settings.AUTH_PROXY_STAFF_ROLES))

        if user.is_superuser != is_superuser or user.is_staff != is_staff:
            user.is_superuser = is_superuser
            user.is_staff = is_staff
            user.save(update_fields=["is_superuser", "is_staff"])
