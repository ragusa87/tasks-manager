"""
Helpers to read claims from the auth-proxy JWT (the ``AUTH_TOKEN`` cookie).

The token is issued by Keycloak and validated by the reverse proxy (traefik
keycloakopenid plugin) *before* the request ever reaches Django. We therefore
only read its claims and deliberately do NOT verify the signature here: we have
neither the signing key nor a reason to re-check what the proxy already
enforced.

Both callers — ``TraefikKeycloakRemoteUserMiddleware._sync_roles`` and
``LogoutView._redirect_url`` — read these claims only when the trusted
``X-Token-User-Name`` header is present. The proxy sets that header only after
validating the session and strips any client-supplied copy, so the cookie is
never trusted on its own: a forged cookie can neither escalate a user nor
redirect logout to an attacker-chosen URL.

Everything in this module is a pure function of its inputs so it can be tested
without a request, a database, or a live Keycloak.
"""

import base64
import binascii
import json
import logging
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


def decode_jwt_claims(token):
    """
    Decode the payload (claims) of a JWT without verifying its signature.

    Returns an empty dict for anything that is not a well-formed JWT, so
    callers never have to guard against ``None`` or malformed cookies.
    """
    if not token:
        return {}

    parts = token.split(".")
    if len(parts) != 3:
        return {}

    payload = parts[1]
    # JWT uses base64url without padding; restore it before decoding.
    payload += "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload)
        claims = json.loads(decoded)
    except (binascii.Error, ValueError):
        logger.warning("Ignoring malformed auth-proxy JWT")
        return {}

    return claims if isinstance(claims, dict) else {}


def client_roles(claims, client):
    """
    Return the roles the token grants for a single OAuth client.

    These live under ``resource_access.<client>.roles`` and are scoped to that
    client — unlike the global ``realm_access.roles`` — so they carry exactly
    the roles assigned to this application's user (e.g. ``staff``,
    ``superuser``). The client name is configurable (see
    ``AUTH_PROXY_OAUTH_CLIENT``). Returns an empty set when ``client`` is falsy
    or absent from the token.
    """
    if not client:
        return set()

    resource_access = claims.get("resource_access") or {}
    client_access = resource_access.get(client) or {}
    return set(client_access.get("roles") or [])


def logout_url_from_claims(claims, post_logout_redirect_uri=None):
    """
    Build the Keycloak end-session endpoint from the token's issuer.

    Keycloak exposes it at ``<iss>/protocol/openid-connect/logout``. The client
    id (``azp``) is passed so Keycloak skips the confirmation prompt, and an
    optional ``post_logout_redirect_uri`` sends the user back to the app (it
    must be registered as a valid post-logout redirect on the Keycloak client).

    Returns ``None`` when the token carries no issuer, so the caller can fall
    back to its configured logout URL.
    """
    issuer = claims.get("iss")
    if not issuer:
        return None

    url = f"{issuer.rstrip('/')}/protocol/openid-connect/logout"

    params = {}
    client = claims.get("azp")
    if client:
        params["client_id"] = client
    if post_logout_redirect_uri:
        params["post_logout_redirect_uri"] = post_logout_redirect_uri

    if params:
        url = f"{url}?{urlencode(params)}"
    return url
