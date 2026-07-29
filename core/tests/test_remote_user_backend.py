from django.contrib.auth import get_user_model
from django.contrib.auth.middleware import AuthenticationMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase, override_settings

from core.auth.remote_user_backend import AuthcrunchRemoteUserMiddleware

USER_HEADER = "HTTP_X_TOKEN_USER_NAME"
ROLE_HEADER = "HTTP_X_TOKEN_USER_ROLES"


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
