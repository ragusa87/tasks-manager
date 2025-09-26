from django.test import TestCase

from task_processor.search import FilterCategory, FilterOption, SearchParser


class TestGenerateFutureQuery(TestCase):
    """Test the generate_future_query functionality"""

    def setUp(self):
        self.parser = SearchParser()

    def test_exclusive_filter_strategy_inactive_to_active(self):
        """Test exclusive strategy: adding a new filter removes others of same field"""
        current_query = "in:inbox"
        target_filter = FilterOption(
            label="Next Actions",
            filter_query="in:next",
            icon="lucide-zap",
            color="blue",
            category=FilterCategory.STATUS
        )
        current_state = {"active": False, "inversed": False}

        result = self.parser.generate_future_query(current_query, target_filter, current_state)
        self.assertEqual(result, "in:next")

    def test_exclusive_filter_strategy_active_to_inactive(self):
        """Test exclusive strategy: removing active filter"""
        current_query = "in:next"
        target_filter = FilterOption(
            label="Next Actions",
            filter_query="in:next",
            icon="lucide-zap",
            color="blue",
            category=FilterCategory.STATUS
        )
        current_state = {"active": True, "inversed": False}

        result = self.parser.generate_future_query(current_query, target_filter, current_state)
        self.assertEqual(result, "")

    def test_exclusive_filter_strategy_with_multiple_existing(self):
        """Test exclusive strategy with multiple existing filters of same field"""
        current_query = "in:inbox priority:high"
        target_filter = FilterOption(
            label="Urgent Priority",
            filter_query="priority:urgent",
            icon="lucide-circle-alert",
            color="red",
            category=FilterCategory.PRIORITY
        )
        current_state = {"active": False, "inversed": False}

        result = self.parser.generate_future_query(current_query, target_filter, current_state)
        self.assertEqual(result, "in:inbox priority:urgent")

    def test_normal_filter_strategy_inactive_to_active(self):
        """Test normal strategy: adding filter to included"""
        current_query = "in:inbox"
        target_filter = FilterOption(
            label="Has Project",
            filter_query="has:project",
            icon="lucide-folder",
            color="blue",
            category=FilterCategory.RELATIONSHIP
        )
        current_state = {"active": False, "inversed": False}

        result = self.parser.generate_future_query(current_query, target_filter, current_state)
        self.assertEqual(result, "in:inbox has:project")

    def test_normal_filter_strategy_active_to_inactive(self):
        """Test normal strategy: removing active filter"""
        current_query = "in:inbox has:project"
        target_filter = FilterOption(
            label="Has Project",
            filter_query="has:project",
            icon="lucide-folder",
            color="blue",
            category=FilterCategory.RELATIONSHIP
        )
        current_state = {"active": True, "inversed": False}

        result = self.parser.generate_future_query(current_query, target_filter, current_state)
        self.assertEqual(result, "in:inbox")

    def test_normal_filter_strategy_multiple_same_category(self):
        """Test normal strategy allows multiple filters of same category"""
        current_query = "has:project"
        target_filter = FilterOption(
            label="Has Context",
            filter_query="has:context",
            icon="lucide-hash",
            color="blue",
            category=FilterCategory.RELATIONSHIP
        )
        current_state = {"active": False, "inversed": False}

        result = self.parser.generate_future_query(current_query, target_filter, current_state)
        self.assertEqual(result, "has:project,context")

    def test_invert_filter_strategy_inactive_to_active(self):
        """Test invert strategy: inactive -> active (included)"""
        current_query = "in:inbox"
        target_filter = FilterOption(
            label="Work Area",
            filter_query='area:"Work"',
            icon="lucide-target",
            color="green",
            category=FilterCategory.AREA
        )
        current_state = {"active": False, "inversed": False}

        result = self.parser.generate_future_query(current_query, target_filter, current_state)
        self.assertEqual(result, 'in:inbox area:work')

    def test_invert_filter_strategy_active_to_inverted(self):
        """Test invert strategy: active (included) -> inverted (excluded)"""
        current_query = 'in:inbox area:"Work"'
        target_filter = FilterOption(
            label="Work Area",
            filter_query='area:"Work"',
            icon="lucide-target",
            color="green",
            category=FilterCategory.AREA
        )
        current_state = {"active": True, "inversed": False}

        result = self.parser.generate_future_query(current_query, target_filter, current_state)
        self.assertEqual(result, 'in:inbox area:Work -area:work')

    def test_invert_filter_strategy_inverted_to_inactive(self):
        """Test invert strategy: inverted (excluded) -> inactive (removed)"""
        current_query = 'in:inbox -area:"Work"'
        target_filter = FilterOption(
            label="Work Area",
            filter_query='area:"Work"',
            icon="lucide-target",
            color="green",
            category=FilterCategory.AREA
        )
        current_state = {"active": True, "inversed": True}

        result = self.parser.generate_future_query(current_query, target_filter, current_state)
        self.assertEqual(result, 'in:inbox -area:Work')

    def test_generate_future_query_with_free_text(self):
        """Test that free text is preserved in generated queries"""
        current_query = "in:inbox search text"
        target_filter = FilterOption(
            label="High Priority",
            filter_query="priority:high",
            icon="lucide-arrow-up",
            color="red",
            category=FilterCategory.PRIORITY
        )
        current_state = {"active": False, "inversed": False}

        result = self.parser.generate_future_query(current_query, target_filter, current_state)
        self.assertEqual(result, "in:inbox priority:high search text")

    def test_generate_future_query_with_quoted_values(self):
        """Test handling of quoted filter values"""
        current_query = 'context:"@home"'
        target_filter = FilterOption(
            label="Office Context",
            filter_query='context:"@office"',
            icon="lucide-hash",
            color="purple",
            category=FilterCategory.CONTEXT
        )
        current_state = {"active": False, "inversed": False}

        result = self.parser.generate_future_query(current_query, target_filter, current_state)
        self.assertEqual(result, 'context:"@home","@office"')

    def test_generate_future_query_with_comma_separated_values(self):
        """Test handling of comma-separated filter values"""
        current_query = 'tags:"work","urgent"'
        target_filter = FilterOption(
            label="Personal Tag",
            filter_query='tags:"personal"',
            icon="lucide-hash",
            color="purple",
            category=FilterCategory.CONTEXT  # contexts use normal strategy
        )
        current_state = {"active": False, "inversed": False}

        result = self.parser.generate_future_query(current_query, target_filter, current_state)
        # Should add to existing values
        self.assertEqual(result, 'tags:work,urgent,personal')

    def test_generate_future_query_empty_current_query(self):
        """Test generating future query from empty current query"""
        current_query = ""
        target_filter = FilterOption(
            label="Inbox",
            filter_query="in:inbox",
            icon="lucide-inbox",
            color="blue",
            category=FilterCategory.STATUS
        )
        current_state = {"active": False, "inversed": False}

        result = self.parser.generate_future_query(current_query, target_filter, current_state)
        self.assertEqual(result, "in:inbox")

    def test_generate_future_query_invalid_filter(self):
        """Test handling of invalid filter query"""
        current_query = "in:inbox"
        target_filter = FilterOption(
            label="Invalid",
            filter_query="invalid_format",  # No field:value format
            icon="lucide-x",
            color="red",
            category=FilterCategory.STATUS
        )
        current_state = {"active": False, "inversed": False}

        result = self.parser.generate_future_query(current_query, target_filter, current_state)
        # Should return unchanged query for invalid filter
        self.assertEqual(result, "in:inbox")

    def test_generate_future_query_complex_scenario(self):
        """Test complex scenario with multiple filters and strategies"""
        current_query = 'in:inbox priority:high has:project area:"Work" search terms'
        target_filter = FilterOption(
            label="Next Actions",
            filter_query="in:next",
            icon="lucide-zap",
            color="blue",
            category=FilterCategory.STATUS  # Exclusive strategy
        )
        current_state = {"active": False, "inversed": False}

        result = self.parser.generate_future_query(current_query, target_filter, current_state)
        # Should replace in:inbox with in:next, keep others
        self.assertEqual(result, 'priority:high has:project area:Work in:next search terms')

    def test_generate_future_query_project_filter_with_id(self):
        """Test project filter with numeric ID"""
        current_query = "in:inbox"
        target_filter = FilterOption(
            label="My Project",
            filter_query="project:123",
            icon="lucide-briefcase",
            color="purple",
            category=FilterCategory.PROJECT
        )
        current_state = {"active": False, "inversed": False}

        result = self.parser.generate_future_query(current_query, target_filter, current_state)
        self.assertEqual(result, "in:inbox project:123")

    def test_generate_future_query_due_date_filter(self):
        """Test due date filter handling"""
        current_query = "in:next"
        target_filter = FilterOption(
            label="Due Today",
            filter_query="is:due",
            icon="lucide-calendar",
            color="orange",
            category=FilterCategory.DUE
        )
        current_state = {"active": False, "inversed": False}

        result = self.parser.generate_future_query(current_query, target_filter, current_state)
        self.assertEqual(result, "in:next is:due")

    def test_generate_future_query_energy_filter(self):
        """Test energy filter handling"""
        current_query = "in:next priority:high"
        target_filter = FilterOption(
            label="High Energy",
            filter_query="energy:high",
            icon="lucide-battery-full",
            color="yellow",
            category=FilterCategory.ENERGY
        )
        current_state = {"active": False, "inversed": False}

        result = self.parser.generate_future_query(current_query, target_filter, current_state)
        self.assertEqual(result, "in:next priority:high energy:high")

    def test_generate_future_query_replacing_energy_filter(self):
        """Test replacing existing energy filter (exclusive strategy)"""
        current_query = "in:next energy:low"
        target_filter = FilterOption(
            label="High Energy",
            filter_query="energy:high",
            icon="lucide-battery-full",
            color="yellow",
            category=FilterCategory.ENERGY
        )
        current_state = {"active": False, "inversed": False}

        result = self.parser.generate_future_query(current_query, target_filter, current_state)
        self.assertEqual(result, "in:next energy:high")

    def test_generate_future_query_context_filter_normal_strategy(self):
        """Test context filter with normal strategy (additive)"""
        current_query = 'context:"@home"'
        target_filter = FilterOption(
            label="Office Context",
            filter_query='context:"@office"',
            icon="lucide-hash",
            color="purple",
            category=FilterCategory.CONTEXT
        )
        current_state = {"active": False, "inversed": False}

        result = self.parser.generate_future_query(current_query, target_filter, current_state)
        self.assertEqual(result, 'context:"@home","@office"')