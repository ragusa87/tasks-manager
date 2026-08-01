import base64
import json

from django.test import SimpleTestCase

from core.auth.jwt import client_roles, decode_jwt_claims, logout_url_from_claims


def make_token(payload):
    """Build a JWT-shaped string (header.payload.signature) for tests."""
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"header.{body}.signature"


# A trimmed-down copy of a real Keycloak access token payload.
SAMPLE_CLAIMS = {
    "iss": "https://keycloak.example.com/realms/example",
    "azp": "tasks",
    "realm_access": {"roles": ["offline_access", "superadmin"]},
    "resource_access": {
        "account": {"roles": ["view-profile"]},
        "tasks": {"roles": ["restricted-access", "staff", "superuser"]},
    },
}


class DecodeJwtClaimsTest(SimpleTestCase):
    def test_decodes_payload(self):
        claims = decode_jwt_claims(make_token(SAMPLE_CLAIMS))

        assert claims["azp"] == "tasks"
        assert claims["resource_access"]["tasks"]["roles"] == [
            "restricted-access",
            "staff",
            "superuser",
        ]

    def test_empty_token_returns_empty_dict(self):
        assert decode_jwt_claims("") == {}
        assert decode_jwt_claims(None) == {}

    def test_non_jwt_shaped_token_returns_empty_dict(self):
        assert decode_jwt_claims("not-a-jwt") == {}
        assert decode_jwt_claims("only.two") == {}

    def test_malformed_payload_returns_empty_dict(self):
        assert decode_jwt_claims("header.@@notbase64@@.sig") == {}

    def test_non_object_payload_returns_empty_dict(self):
        assert decode_jwt_claims(make_token([1, 2, 3])) == {}


class ClientRolesTest(SimpleTestCase):
    def test_reads_roles_for_the_configured_client(self):
        assert client_roles(SAMPLE_CLAIMS, "tasks") == {
            "restricted-access",
            "staff",
            "superuser",
        }

    def test_does_not_leak_other_clients_or_realm_roles(self):
        roles = client_roles(SAMPLE_CLAIMS, "tasks")

        assert "view-profile" not in roles  # account client
        assert "superadmin" not in roles  # realm_access

    def test_missing_client_returns_empty_set(self):
        assert client_roles(SAMPLE_CLAIMS, "unknown") == set()
        assert client_roles(SAMPLE_CLAIMS, "") == set()
        assert client_roles({}, "tasks") == set()


class LogoutUrlFromClaimsTest(SimpleTestCase):
    def test_builds_end_session_endpoint_with_client_id(self):
        url = logout_url_from_claims(SAMPLE_CLAIMS)

        assert url == (
            "https://keycloak.example.com/realms/example"
            "/protocol/openid-connect/logout?client_id=tasks"
        )

    def test_includes_post_logout_redirect_uri(self):
        url = logout_url_from_claims(
            SAMPLE_CLAIMS, post_logout_redirect_uri="https://tasks.example.com/"
        )

        assert "post_logout_redirect_uri=https%3A%2F%2Ftasks.example.com%2F" in url

    def test_missing_issuer_returns_none(self):
        assert logout_url_from_claims({}) is None
