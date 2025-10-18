import hashlib
import hmac

from django.conf import settings
from django.urls import reverse


def generate_download_token(document_id: int):
    """
    Generate a secure token for document download using HMAC-SHA256.

    Args:
        document_id: The document ID to generate token for

    Returns:
        str: Hex-encoded HMAC token
    """
    message = f"document_download_{str(document_id)}"
    token = hmac.new(
        settings.SECRET_KEY.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return token


def validate_download_token(document_id, provided_token):
    """
    Validate a download token against the document ID.

    Args:
        document_id: The document ID
        provided_token: Token provided in the request

    Returns:
        bool: True if token is valid, False otherwise
    """
    expected_token = generate_download_token(document_id)
    return hmac.compare_digest(expected_token, provided_token)


def get_download_url(document_id: int):
    """
    Generate a download URL with token for a given document ID.

    Args:
        document_id: The document ID

    Returns:
        str: Download URL with token parameter
    """
    token = generate_download_token(document_id)

    return reverse("document_download", args=[document_id]) + f"?token={token}"
