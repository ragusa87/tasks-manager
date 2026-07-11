from django.test import Client, TestCase


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
