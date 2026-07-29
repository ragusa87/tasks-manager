"""Validation and creation of Item attachments.

Single entry point (:func:`attach_document`) shared by the web upload view
and the API, so the size / MIME / duplicate rules cannot drift between the
two surfaces. ``settings.ALLOWED_TYPES`` and ``settings.MAX_FILE_SIZE`` are
the policy.
"""

import magic
from django.conf import settings
from django.db import IntegrityError, transaction

from core.upload_types import describe_types
from task_processor.models import Document
from task_processor.models.document import compute_content_hash


class DocumentValidationError(Exception):
    """str(exc) is the human-readable reason, without the file-name prefix."""


def attach_document(item, user, file, batch_hashes=None) -> Document:
    """Validate ``file`` and create a Document on ``item``.

    ``batch_hashes`` (an optional set) enables duplicate detection within a
    multi-file batch; the hash of a successfully attached file is added to it.
    Raises :class:`DocumentValidationError` when the file is rejected.
    """
    max_size = settings.MAX_FILE_SIZE
    allowed_types = settings.ALLOWED_TYPES

    if file.size > max_size:
        raise DocumentValidationError(
            f"file exceeds the {max_size // (1024 * 1024)} MB limit"
        )

    # Validate file type using magic bytes, not the browser-supplied Content-Type.
    detected_type = magic.from_buffer(file.read(2048), mime=True)
    file.seek(0)
    if allowed_types and detected_type not in allowed_types:
        raise DocumentValidationError(
            f"file type not allowed ({describe_types(allowed_types)})"
        )

    # Refuse content already attached to this item (or duplicated within the
    # current batch), regardless of file name.
    content_hash = compute_content_hash(file)
    if (
        batch_hashes is not None and content_hash in batch_hashes
    ) or item.documents.filter(content_hash=content_hash).exists():
        raise DocumentValidationError("identical file already attached")

    try:
        # The exists() check above is advisory (nice error message); the
        # unique (item, content_hash) constraint is what actually prevents
        # duplicates when two identical uploads race each other.
        with transaction.atomic():
            document = Document.objects.create(
                item=item,
                file=file,
                # Keep the tail so the extension survives the column limit.
                file_name=file.name[-Document.FILE_NAME_MAX_LENGTH :],
                file_size=file.size,
                content_type=detected_type,
                content_hash=content_hash,
                user=user,
            )
    except IntegrityError:
        raise DocumentValidationError("identical file already attached")
    if batch_hashes is not None:
        batch_hashes.add(content_hash)
    return document
