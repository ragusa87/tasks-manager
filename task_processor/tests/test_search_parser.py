from django.test import TestCase

from task_processor.search import SearchParser


class TestSearchParser(TestCase):
    """Test the search query parser functionality"""

    def setUp(self):
        self.parser = SearchParser()

    def test_empty_query(self):
        """Test parsing empty query"""
        result = self.parser.parse("")
        self.assertEqual(result.original_query, "")
        self.assertEqual(result.included, {})
        self.assertEqual(result.excluded, {})
        self.assertEqual(result.query, "")

    def test_simple_field_filter(self):
        """Test parsing simple field filters"""
        result = self.parser.parse("in:inbox")
        self.assertEqual(result.included, {"in": ["inbox"]})
        self.assertEqual(result.excluded, {})
        self.assertEqual(result.query, "")

    def test_excluded_field_filter(self):
        """Test parsing excluded field filters"""
        result = self.parser.parse("-in:inbox")
        self.assertEqual(result.included, {})
        self.assertEqual(result.excluded, {"in": ["inbox"]})
        self.assertEqual(result.query, "")

    def test_quoted_values(self):
        """Test parsing quoted field values"""
        result = self.parser.parse('tags:"my tag"')
        self.assertEqual(result.included, {"tags": ["my tag"]})
        self.assertEqual(result.query, "")

    def test_multiple_quoted_values(self):
        """Test parsing multiple quoted values"""
        result = self.parser.parse('tags:"coucou","my god"')
        self.assertEqual(result.included, {"tags": ["coucou", "my god"]})
        self.assertEqual(result.query, "")

    def test_mixed_included_and_excluded(self):
        """Test parsing both included and excluded filters"""
        result = self.parser.parse("in:inbox -priority:low")
        self.assertEqual(result.included, {"in": ["inbox"]})
        self.assertEqual(result.excluded, {"priority": ["low"]})
        self.assertEqual(result.query, "")

    def test_complex_query_example(self):
        """Test the example query from the requirements"""
        query = 'in:inbox tags:"train","bus" is:overdue priority:-low coucou'
        result = self.parser.parse(query)

        expected_included = {
            "in": ["inbox"],
            "tags": ["train", "bus"],
            "is": ["overdue"],
            "priority": [
                "-low"
            ],  # Note: priority:-low is parsed as included field with value "-low"
        }
        expected_excluded = {}

        self.assertEqual(result.included, expected_included)
        self.assertEqual(result.excluded, expected_excluded)
        self.assertEqual(result.query, "coucou")

    def test_excluded_priority_example(self):
        """Test parsing excluded priority filter"""
        query = "in:inbox -priority:low coucou"
        result = self.parser.parse(query)

        expected_included = {"in": ["inbox"]}
        expected_excluded = {
            "priority": ["low"]  # This is how you exclude priority:low
        }

        self.assertEqual(result.included, expected_included)
        self.assertEqual(result.excluded, expected_excluded)
        self.assertEqual(result.query, "coucou")

    def test_free_text_only(self):
        """Test parsing free text without field filters"""
        result = self.parser.parse("search for this text")
        self.assertEqual(result.included, {})
        self.assertEqual(result.excluded, {})
        self.assertEqual(result.query, "search for this text")

    def test_mixed_field_and_free_text(self):
        """Test parsing with both field filters and free text"""
        result = self.parser.parse("in:inbox some free text tags:work")
        self.assertEqual(result.included, {"in": ["inbox"], "tags": ["work"]})
        self.assertEqual(result.query, "some free text")

    def test_comma_separated_unquoted_values(self):
        """Test parsing comma-separated values without quotes"""
        result = self.parser.parse("tags:work,personal,urgent")
        self.assertEqual(result.included, {"tags": ["work", "personal", "urgent"]})

    def test_multiple_fields_same_name(self):
        """Test parsing multiple instances of the same field"""
        result = self.parser.parse("tags:work tags:personal")
        self.assertEqual(result.included, {"tags": ["work", "personal"]})

    def test_special_characters_in_values(self):
        """Test parsing values with special characters"""
        result = self.parser.parse('tags:"work-item" priority:high+urgent')
        self.assertEqual(
            result.included, {"tags": ["work-item"], "priority": ["high+urgent"]}
        )

    def test_whitespace_handling(self):
        """Test proper whitespace handling"""
        result = self.parser.parse("  in:inbox   tags:work   some   text  ")
        self.assertEqual(result.included, {"in": ["inbox"], "tags": ["work"]})
        self.assertEqual(result.query, "some text")

    def test_original_query_preserved(self):
        """Test that original query is preserved"""
        original = 'in:inbox tags:"test" some text'
        result = self.parser.parse(original)
        self.assertEqual(result.original_query, original)
