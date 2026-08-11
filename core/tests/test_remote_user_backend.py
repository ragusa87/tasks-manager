import base64
import json

from django.contrib.auth import get_user_model
from django.contrib.auth.middleware import AuthenticationMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase, override_settings

from core.auth.remote_user_backend import (
    AuthcrunchRemoteUserMiddleware,
    TraefikKeycloakRemoteUserMiddleware,
)

USER_HEADER = "HTTP_X_TOKEN_USER_NAME"
ROLE_HEADER = "HTTP_X_TOKEN_USER_ROLES"
COOKIE_NAME = "AUTH_TOKEN"


def make_token(tasks_roles):
    """Build a proxy JWT carrying the given roles on the `tasks` client."""
    payload = {
        "iss": "https://keycloak.example.com/realms/example",
        "azp": "tasks",
        "resource_access": {"tasks": {"roles": tasks_roles}},
    }
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"header.{body}.signature"


@override_settings(
    AUTHENTICATION_BACKENDS=[
        "core.auth.remote_user_backend.AuthcrunchRemoteUserBackend"
    ]
)
class AuthcrunchRemoteUserMiddlewareTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = AuthcrunchRemoteUserMiddleware(lambda request: None)

    def _request(self, path="/", session=None, **headers):
        request = self.factory.get(path, **headers)
        SessionMiddleware(lambda r: None).process_request(request)
        if session is not None:
            request.session = session
        AuthenticationMiddleware(lambda r: None).process_request(request)
        self.middleware.process_request(request)
        return request

    def test_header_logs_the_user_in(self):
        request = self._request(**{USER_HEADER: "alice"})

        assert request.user.is_authenticated
        assert request.user.username == "alice"
        assert request.user.is_staff
        assert not request.user.is_superuser
        assert get_user_model().objects.filter(username="alice").exists()

    def test_admin_role_grants_superuser(self):
        request = self._request(
            **{USER_HEADER: "alice", ROLE_HEADER: "authp/user authp/admin"}
        )

        assert request.user.is_superuser

    def test_session_survives_requests_without_header(self):
        # The reverse proxy does not set the header on /api/* routes; the
        # session established on regular pages must carry the user through
        # them instead of being flushed (which would also rotate the CSRF
        # secret under every open page).
        page_request = self._request(**{USER_HEADER: "alice"})

        api_request = self._request("/api/items", session=page_request.session)

        assert api_request.user.is_authenticated
        assert api_request.user.username == "alice"

    def test_anonymous_without_header_stays_anonymous(self):
        request = self._request("/api/items")

        assert not request.user.is_authenticated

    @override_settings(REMOTE_USER_FORCE_LOGOUT=True)
    def test_force_logout_drops_the_session_user_without_header(self):
        # Development mode: the session never outlives the header.
        page_request = self._request(**{USER_HEADER: "alice"})

        api_request = self._request("/api/items", session=page_request.session)

        assert not api_request.user.is_authenticated


@override_settings(
    AUTHENTICATION_BACKENDS=["django.contrib.auth.backends.RemoteUserBackend"],
    AUTH_PROXY_COOKIE_NAME=COOKIE_NAME,
    AUTH_PROXY_OAUTH_CLIENT="tasks",
    AUTH_PROXY_SUPERUSER_ROLES=["superuser"],
    AUTH_PROXY_STAFF_ROLES=["staff"],
)
class TraefikKeycloakRemoteUserMiddlewareTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = TraefikKeycloakRemoteUserMiddleware(lambda request: None)

    def _request(self, path="/", session=None, cookies=None, **headers):
        request = self.factory.get(path, **headers)
        if cookies:
            request.COOKIES.update(cookies)
        SessionMiddleware(lambda r: None).process_request(request)
        if session is not None:
            request.session = session
        AuthenticationMiddleware(lambda r: None).process_request(request)
        self.middleware.process_request(request)
        return request

    def test_superuser_role_grants_superuser_and_staff(self):
        request = self._request(
            cookies={COOKIE_NAME: make_token(["superuser"])},
            **{USER_HEADER: "alice"},
        )

        assert request.user.is_superuser
        assert request.user.is_staff

    def test_staff_role_grants_staff_but_not_superuser(self):
        request = self._request(
            cookies={COOKIE_NAME: make_token(["staff"])},
            **{USER_HEADER: "bob"},
        )

        assert request.user.is_staff
        assert not request.user.is_superuser

    def test_unmapped_roles_grant_nothing(self):
        request = self._request(
            cookies={COOKIE_NAME: make_token(["restricted-access"])},
            **{USER_HEADER: "carol"},
        )

        assert not request.user.is_staff
        assert not request.user.is_superuser

    def test_flags_persist_to_the_database(self):
        self._request(
            cookies={COOKIE_NAME: make_token(["superuser"])},
            **{USER_HEADER: "dave"},
        )

        stored = get_user_model().objects.get(username="dave")
        assert stored.is_superuser
        assert stored.is_staff

    def test_roles_not_synced_from_cookie_without_the_trusted_header(self):
        # The proxy sets no header on /api/* but the browser still sends the
        # cookie; a forged cookie there must NOT escalate the user. The flags
        # from the last real page request are kept instead.
        page_request = self._request(
            cookies={COOKIE_NAME: make_token(["staff"])},
            **{USER_HEADER: "erin"},
        )

        api_request = self._request(
            "/api/items",
            session=page_request.session,
            cookies={COOKIE_NAME: make_token(["superuser"])},
        )

        assert not api_request.user.is_superuser  # escalation prevented
        assert api_request.user.is_staff  # retained from the page request

    def test_roles_resynced_when_token_changes(self):
        first = self._request(
            cookies={COOKIE_NAME: make_token(["superuser"])},
            **{USER_HEADER: "frank"},
        )

        second = self._request(
            session=first.session,
            cookies={COOKIE_NAME: make_token(["staff"])},
            **{USER_HEADER: "frank"},
        )

        assert not second.user.is_superuser
        assert second.user.is_staff
