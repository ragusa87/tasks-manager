from django.conf import settings
from django.utils.functional import lazy
from ninja import File, Router, UploadedFile
from ninja.errors import HttpError
from ninja.responses import Status

from core.upload_types import describe_types
from task_processor.api.schemas import DocumentOut
from task_processor.models import Document, Item
from task_processor.uploads import DocumentValidationError, attach_document

router = Router(tags=["documents"])


def upload_document(user, item_id: int, file) -> Document:
    """Attach one uploaded file to the user's item (HTTP-free unit)."""
    item = Item.objects.filter(user=user, pk=item_id).first()
    if item is None:
        # Same 404 for missing and foreign items: don't leak existence.
        raise HttpError(404, "Item not found")
    try:
        return attach_document(item, user, file)
    except DocumentValidationError as error:
        raise HttpError(422, f"{file.name}: {error}")


def _upload_description() -> str:
    """OpenAPI description derived from the upload settings."""
    return (
        f"Upload one file as a multipart `file` part. "
        f"Maximum size: {settings.MAX_FILE_SIZE // (1024 * 1024)} MB. "
        f"Allowed types: {describe_types(settings.ALLOWED_TYPES)} "
        f"({', '.join(settings.ALLOWED_TYPES)}). "
        f"The file type is detected from the content, not the file name. "
        f"Duplicate content (same SHA-256) on the same item is rejected "
        f"with 422."
    )


# Multipart with a single named `file` part. Future per-document metadata
# (description, transcript, ...) can be added non-breakingly as an optional
# `payload: Form[...]` schema alongside the file part.
@router.post(
    "/items/{item_id}/documents",
    response={201: DocumentOut},
    summary="Attach a document to an item",
    # Lazy so the docs reflect the settings at request time, not the values
    # frozen at import (the OpenAPI schema is rebuilt per request and
    # DjangoJSONEncoder resolves lazy strings when serializing).
    description=lazy(_upload_description, str)(),
)
def upload_document_endpoint(request, item_id: int, file: UploadedFile = File(...)):
    return Status(201, upload_document(request.user, item_id, file))
