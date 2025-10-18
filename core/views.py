import os

from django.core.exceptions import PermissionDenied
from django.http import FileResponse, HttpResponseServerError
from django.shortcuts import get_object_or_404
from django.views import View
from factory.django import get_model

from core.filesystem_backends.helper import get_file_system_engine
from core.token import validate_download_token


class DocumentDownloadView(View):
    """
    View to serve documents by document ID.
    Retrieves the file using get_file_system_engine() and deletes it after download.
    """

    def get(self, request, document_id):
        # Validate token parameter
        provided_token = request.GET.get("token")
        if not provided_token:
            raise PermissionDenied("Token parameter is required")

        if not validate_download_token(document_id, provided_token):
            raise PermissionDenied("Invalid token")

        # Get the document from the database
        Document = get_model("task_processor", "Document")
        document = get_object_or_404(Document, id=document_id)

        try:
            # Get file system engine
            engine = get_file_system_engine()

            # Fetch the file to temporary storage
            temp_file_path, original_filename = engine.fetch_file_to_temp(
                document.file_path
            )

            # Create file response
            response = FileResponse(
                open(temp_file_path, "rb"),
                as_attachment=True,
                filename=document.original_filename or original_filename,
            )

            # Set content type if available
            if document.mime_type:
                response["Content-Type"] = document.mime_type

            # Add a callback to delete the file after response is sent
            def cleanup_file():
                try:
                    if os.path.exists(temp_file_path):
                        os.remove(temp_file_path)
                except OSError:
                    pass  # Ignore errors during cleanup

            # Schedule cleanup when response closes
            response.close_callback = cleanup_file

            return response

        except Exception as e:
            raise HttpResponseServerError(f"Document could not be retrieved: {str(e)}")
