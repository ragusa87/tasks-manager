from django.test import Client, TestCase, override_settings


class TestApiDocs(TestCase):
    """Smoke tests for the auto-generated OpenAPI documentation."""

    def setUp(self):
        self.client = Client()

    def test_docs_page_renders(self):
        response = self.client.get("/api/docs")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"swagger", response.content.lower())

    def test_openapi_json_lists_endpoints(self):
        response = self.client.get("/api/openapi.json")
        self.assertEqual(response.status_code, 200)
        paths = response.json()["paths"]
        self.assertIn("/api/items", paths)
        self.assertIn("/api/tags", paths)
        self.assertIn("/api/contexts", paths)
        self.assertIn("/api/areas", paths)
        self.assertIn("/api/items/{item_id}/documents", paths)

    @override_settings(
        MAX_FILE_SIZE=5 * 1024 * 1024,
        ALLOWED_TYPES=["application/pdf", "image/png"],
    )
    def test_document_upload_docs_state_limits(self):
        """The upload docs reflect MAX_FILE_SIZE / ALLOWED_TYPES.

        The description is lazy, so the overridden settings (not the real
        ones, which may change) are what the schema must show.
        """
        response = self.client.get("/api/openapi.json")
        operation = response.json()["paths"]["/api/items/{item_id}/documents"]["post"]
        description = operation["description"]
        self.assertIn("5 MB", description)
        self.assertIn("PDF or image", description)
        self.assertIn("application/pdf, image/png", description)
