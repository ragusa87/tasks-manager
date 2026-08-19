"""Cloudflare Turnstile verification for the login form.

Kept as a small, HTTP-free-to-test unit: :func:`verify_turnstile` is the only
network call and is trivially mockable. The login view calls
:func:`captcha_enabled` to decide whether to render the widget / enforce the
check, so the feature is fully off (and login behaves exactly as before) unless
the flag *and* both keys are set.
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

# Field name Turnstile injects into the submitted form.
TOKEN_FIELD = "cf-turnstile-response"


def captcha_enabled() -> bool:
    """True only when the flag is on and both keys are configured."""
    return bool(
        settings.LOGIN_CAPTCHA_ENABLED
        and settings.TURNSTILE_SITE_KEY
        and settings.TURNSTILE_SECRET_KEY
    )


def verify_turnstile(token: str, remote_ip: str | None = None) -> bool:
    """Validate a Turnstile token against Cloudflare's siteverify endpoint.

    Returns True when the captcha is disabled (no-op). When enabled, returns
    True only on a successful verification and fails closed on a missing token,
    a network error, or a malformed response.
    """
    if not captcha_enabled():
        return True
    if not token:
        return False

    data = {"secret": settings.TURNSTILE_SECRET_KEY, "response": token}
    if remote_ip:
        data["remoteip"] = remote_ip
    try:
        response = requests.post(SITEVERIFY_URL, data=data, timeout=5)
        return bool(response.json().get("success"))
    except (requests.RequestException, ValueError):
        # Provider unreachable or non-JSON body: fail closed so the captcha
        # cannot be bypassed by knocking the verifier offline.
        logger.warning("Turnstile verification request failed", exc_info=True)
        return False
