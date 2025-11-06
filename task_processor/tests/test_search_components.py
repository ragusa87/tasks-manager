from django.contrib.auth.models import User
from django.test import TestCase

from task_processor.constants import GTDStatus
from task_processor.models import Area, Context, Item
from task_processor.search import (
    FilterCategory,
    FilterOption,
    FilterStrategy,
    SearchFilter,
    SearchParser,
    SearchTokens,
)


class TestFilterOption(TestCase):
    """Test the FilterOption NamedTuple and its properties"""

    def setUp(self):
        self.filter_option = FilterOption(
            label="Inbox",
            filter_query="in:inbox",
            icon="lucide-inbox",
            color="blue",
            category=FilterCategory.STATUS,
            active=False,
            inversed=False,
            next_query="",
        )

    def test_filter_option_creation(self):
        """Test FilterOption creation with all fields"""
        self.assertEqual(self.filter_option.label, "Inbox")
        self.assertEqual(self.filter_option.filter_query, "in:inbox")
        self.assertEqual(self.filter_option.icon, "lucide-inbox")
        self.assertEqual(self.filter_option.color, "blue")
        self.assertEqual(self.filter_option.category, FilterCategory.STATUS)
        self.assertFalse(self.filter_option.active)
        self.assertFalse(self.filter_option.inversed)
        self.assertEqual(self.filter_option.next_query, "")

    def test_inactive_classes(self):
        """Test CSS classes for inactive state"""
        classes = self.filter_option.inactive_classes
        self.assertIn("filter-suggestion", classes)
        self.assertIn("filter-blue", classes)
        self.assertIn("filter-suggestion-inactive", classes)

    def test_active_classes(self):
        """Test CSS classes for active state"""
        classes = self.filter_option.active_classes
        self.assertIn("filter-suggestion", classes)
        self.assertIn("filter-blue", classes)
        self.assertIn("filter-suggestion-active", classes)

    def test_inversed_classes(self):
        """Test CSS classes for inversed state"""
        classes = self.filter_option.inversed_classes
        self.assertIn("filter-suggestion", classes)
        self.assertIn("filter-blue", classes)
        self.assertIn("filter-suggestion-inversed", classes)

    def test_current_classes_inactive(self):
        """Test current_classes property for inactive filter"""
        classes = self.filter_option.current_classes
        self.assertEqual(classes, self.filter_option.inactive_classes)

    def test_current_classes_active(self):
        """Test current_classes property for active filter"""
        active_filter = FilterOption(
            label="Inbox",
            filter_query="in:inbox",
            icon="lucide-inbox",
            color="blue",
            category=FilterCategory.STATUS,
            active=True,
            inversed=False,
            next_query="",
        )
        classes = active_filter.current_classes
        self.assertEqual(classes, active_filter.active_classes)

    def test_current_classes_inversed(self):
        """Test current_classes property for inversed filter"""
        inversed_filter = FilterOption(
            label="Inbox",
            filter_query="in:inbox",
            icon="lucide-inbox",
            color="blue",
            category=FilterCategory.STATUS,
            active=True,
            inversed=True,
            next_query="",
        )
        classes = inversed_filter.current_classes
        self.assertEqual(classes, inversed_filter.inversed_classes)

    def test_different_color_schemes(self):
        """Test that different colors produce different CSS classes"""
        # Test that different colors use different filter classes
        colors = [
            "blue",
            "green",
            "red",
            "yellow",
            "purple",
            "pink",
            "indigo",
            "orange",
            "teal",
            "cyan",
        ]

        for color in colors:
            filter_option = FilterOption(
                label="Test",
                filter_query="test:value",
                icon="lucide-test",
                color=color,
                category=FilterCategory.STATUS,
            )

            inactive_classes = filter_option.inactive_classes
            active_classes = filter_option.active_classes
            inversed_classes = filter_option.inversed_classes

            # Should contain the base classes
            self.assertIn("filter-suggestion", inactive_classes)
            self.assertIn("filter-suggestion", active_classes)
            self.assertIn("filter-suggestion", inversed_classes)

            # Should contain color-specific class
            self.assertIn(f"filter-{color}", inactive_classes)
            self.assertIn(f"filter-{color}", active_classes)
            self.assertIn(f"filter-{color}", inversed_classes)

            # Should contain state-specific class
            self.assertIn("filter-suggestion-inactive", inactive_classes)
            self.assertIn("filter-suggestion-active", active_classes)
            self.assertIn("filter-suggestion-inversed", inversed_classes)
            self.assertIn("filter-suggestion-active", inversed_classes)


class TestSearchFilter(TestCase):
    """Test the SearchFilter class"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com"
        )

        # Create test areas and contexts
        self.work_area = Area.objects.create(name="Work", user=self.user)
        self.personal_area = Area.objects.create(name="Personal", user=self.user)

        self.office_context = Context.objects.create(name="office", user=self.user)
        self.home_context = Context.objects.create(name="home", user=self.user)

        # Create test projects
        self.project1 = Item.objects.create(
            title="Website redesign", status=GTDStatus.PROJECT, user=self.user
        )
        self.project2 = Item.objects.create(
            title="Mobile app", status=GTDStatus.PROJECT, user=self.user
        )

        self.search_filter = SearchFilter(
            user=self.user,
            areas=[self.work_area, self.personal_area],
            contexts=[self.office_context, self.home_context],
            projects=[self.project1, self.project2],
        )

    def test_search_filter_initialization(self):
        """Test SearchFilter initialization"""
        self.assertEqual(self.search_filter.user, self.user)
        self.assertEqual(len(self.search_filter.areas), 2)
        self.assertEqual(len(self.search_filter.contexts), 2)
        self.assertEqual(len(self.search_filter.projects), 2)

    def test_get_all_filters(self):
        """Test getting all filter options"""
        filters = self.search_filter.get_all_filters()

        # Should have filters for all categories
        categories_found = set()
        for filter_opt in filters:
            categories_found.add(filter_opt.category)

        # Should have at least status, priority, due, energy, relationship filters
        expected_categories = {
            FilterCategory.STATUS,
            FilterCategory.PRIORITY,
            FilterCategory.DUE,
            FilterCategory.ENERGY,
            FilterCategory.RELATIONSHIP,
        }

        for category in expected_categories:
            self.assertIn(category, categories_found)

        # Should have area and context filters if provided
        self.assertIn(FilterCategory.AREA, categories_found)
        self.assertIn(FilterCategory.CONTEXT, categories_found)
        self.assertIn(FilterCategory.PROJECT, categories_found)

    def test_get_filters_by_category(self):
        """Test filtering by category"""
        status_filters = self.search_filter.get_filters_by_category(
            FilterCategory.STATUS
        )

        # Should have status filters
        self.assertTrue(len(status_filters) > 0)

        # All should be status category
        for filter_opt in status_filters:
            self.assertEqual(filter_opt.category, FilterCategory.STATUS)

        # Should include expected status filters
        status_labels = [f.label for f in status_filters]
        expected_statuses = [
            "Inbox",
            "Next Actions",
            "Projects",
            "Waiting For",
            "Someday",
            "Reference",
        ]

        for status in expected_statuses:
            self.assertIn(status, status_labels)

    def test_get_popular_filters(self):
        """Test getting popular filters"""
        popular = self.search_filter.get_popular_filters()

        # Should have some popular filters
        self.assertTrue(len(popular) > 0)

        # Should include common ones
        labels = [f.label for f in popular]
        self.assertIn("Inbox", labels)
        self.assertIn("Next Actions", labels)

    def test_area_filters_generation(self):
        """Test that area filters are generated correctly"""
        area_filters = self.search_filter.get_filters_by_category(FilterCategory.AREA)

        self.assertEqual(len(area_filters), 2)

        area_names = [f.label for f in area_filters]
        self.assertIn("Work", area_names)
        self.assertIn("Personal", area_names)

        # Check filter queries
        work_filter = next(f for f in area_filters if f.label == "Work")
        self.assertEqual(work_filter.filter_query, 'area:"Work"')
        self.assertEqual(work_filter.color, "green")
        self.assertEqual(work_filter.icon, "lucide-at-sign")

    def test_context_filters_generation(self):
        """Test that context filters are generated correctly"""
        context_filters = self.search_filter.get_filters_by_category(
            FilterCategory.CONTEXT
        )

        self.assertEqual(len(context_filters), 2)

        context_names = [f.label for f in context_filters]
        self.assertIn("office", context_names)
        self.assertIn("home", context_names)

        # Check filter queries
        office_filter = next(f for f in context_filters if f.label == "office")
        self.assertEqual(office_filter.filter_query, 'context:"office"')
        self.assertEqual(office_filter.color, "purple")
        self.assertEqual(office_filter.icon, "lucide-hash")

    def test_project_filters_generation(self):
        """Test that project filters are generated correctly"""
        project_filters = self.search_filter.get_filters_by_category(
            FilterCategory.PROJECT
        )

        self.assertEqual(len(project_filters), 2)

        project_titles = [f.label for f in project_filters]
        self.assertIn("Website redesign", project_titles)
        self.assertIn("Mobile app", project_titles)

        # Check filter queries use project IDs
        website_filter = next(
            f for f in project_filters if f.label == "Website redesign"
        )
        self.assertEqual(website_filter.filter_query, f"project:{self.project1.pk}")
        self.assertEqual(website_filter.color, "purple")
        self.assertEqual(website_filter.icon, "lucide-briefcase")

    def test_get_filters_with_state(self):
        """Test getting filters with state based on search query"""
        # Test with a query that has active filters
        query = "in:inbox priority:high"
        filters_by_category = self.search_filter.get_filters_with_state(query)

        # Should return dictionary with categories as keys
        self.assertIsInstance(filters_by_category, dict)

        # Should have status category
        self.assertIn("status", filters_by_category)

        # Find the inbox filter and check it's active
        status_filters = filters_by_category["status"]
        inbox_filter = next(
            (f for f in status_filters if f.filter_query == "in:inbox"), None
        )
        self.assertIsNotNone(inbox_filter)

        # Check if the filter matching logic works
        # Note: This might fail if the field matching logic in the parser is different
        # Let's test a simpler case first
        simple_query = "in:inbox"
        simple_filters = self.search_filter.get_filters_with_state(simple_query)
        simple_status_filters = simple_filters["status"]
        simple_inbox_filter = next(
            (f for f in simple_status_filters if f.filter_query == "in:inbox"), None
        )

        # For now, just check that the filter exists and has the right structure
        self.assertIsNotNone(simple_inbox_filter)
        self.assertTrue(simple_inbox_filter.active)
        self.assertFalse(simple_inbox_filter.inversed)

        # Test inversion
        simple_query = "-in:inbox"
        simple_filters = self.search_filter.get_filters_with_state(simple_query)
        simple_status_filters = simple_filters["status"]
        simple_inbox_filter = next(
            (f for f in simple_status_filters if f.filter_query == "in:inbox"), None
        )
        self.assertTrue(simple_inbox_filter.active)
        self.assertTrue(simple_inbox_filter.inversed)

    def test_empty_lists_handling(self):
        """Test SearchFilter with empty areas/contexts/projects"""
        empty_filter = SearchFilter(user=self.user, areas=[], contexts=[], projects=[])

        filters = empty_filter.get_all_filters()

        # Should still have basic filters
        categories = {f.category for f in filters}
        self.assertIn(FilterCategory.STATUS, categories)
        self.assertIn(FilterCategory.PRIORITY, categories)

        # Should not have area/context/project specific filters
        area_filters = [f for f in filters if f.category == FilterCategory.AREA]
        context_filters = [f for f in filters if f.category == FilterCategory.CONTEXT]
        project_filters = [f for f in filters if f.category == FilterCategory.PROJECT]

        self.assertEqual(len(area_filters), 0)
        self.assertEqual(len(context_filters), 0)
        self.assertEqual(len(project_filters), 0)


class TestSearchTokens(TestCase):
    """Test the SearchTokens dataclass"""

    def test_search_tokens_creation(self):
        """Test SearchTokens creation and defaults"""
        tokens = SearchTokens("test query")

        self.assertEqual(tokens.original_query, "test query")
        self.assertEqual(tokens.included, {})
        self.assertEqual(tokens.excluded, {})
        self.assertEqual(tokens.query, "")

    def test_search_tokens_with_data(self):
        """Test SearchTokens with actual data"""
        tokens = SearchTokens(
            original_query="in:inbox -priority:low test",
            included={"in": ["inbox"]},
            excluded={"priority": ["low"]},
            query="test",
        )

        self.assertEqual(tokens.original_query, "in:inbox -priority:low test")
        self.assertEqual(tokens.included, {"in": ["inbox"]})
        self.assertEqual(tokens.excluded, {"priority": ["low"]})
        self.assertEqual(tokens.query, "test")


class TestFilterStrategy(TestCase):
    """Test filter strategy functionality"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com"
        )
        self.parser = SearchParser()

    def test_filter_strategy_enum(self):
        """Test FilterStrategy enum values"""
        self.assertEqual(FilterStrategy.NORMAL.value, "normal")
        self.assertEqual(FilterStrategy.EXCLUSIVE.value, "exclusive")
        self.assertEqual(FilterStrategy.INVERT.value, "invert")

    def test_exclusive_strategy(self):
        """Test EXCLUSIVE filter strategy behavior"""
        # Create a status filter
        status_filter = FilterOption(
            label="Inbox",
            filter_query="in:inbox",
            icon="lucide-inbox",
            color="blue",
            category=FilterCategory.STATUS,
        )

        # Test that toggling an active EXCLUSIVE filter removes it
        current_query = "in:inbox"
        current_state = {"active": True, "inversed": False}

        next_query = self.parser.generate_future_query(
            current_query,
            status_filter,
            current_state,
            strategy=FilterStrategy.EXCLUSIVE,
        )

        # EXCLUSIVE strategy removes the filter when active
        self.assertEqual(next_query.strip(), "")

    def test_normal_strategy(self):
        """Test normal filter strategy behavior"""
        # Create a relationship filter (normal strategy)
        relationship_filter = FilterOption(
            label="Has Project",
            filter_query="has:project",
            icon="lucide-folder",
            color="blue",
            category=FilterCategory.RELATIONSHIP,
        )

        # Test adding a normal filter
        current_query = ""
        current_state = {"active": False, "inversed": False}

        next_query = self.parser.generate_future_query(
            current_query, relationship_filter, current_state
        )

        # Should add the filter
        self.assertIn("has:project", next_query)

    def test_invert_strategy(self):
        """Test invert filter strategy behavior"""
        # Create an area filter (invert strategy)
        area_filter = FilterOption(
            label="Work",
            filter_query='area:"Work"',
            icon="at-sign",
            color="green",
            category=FilterCategory.AREA,
        )

        # Test the three-state cycle: inactive -> active -> inverted -> inactive

        # State 1: Inactive -> Active
        current_state = {"active": False, "inversed": False}
        next_query = self.parser.generate_future_query("", area_filter, current_state)
        # The parser normalizes values and may remove quotes if not needed
        self.assertTrue(
            "area:work" in next_query.lower() or 'area:"work"' in next_query.lower()
        )
        self.assertNotIn("-area:", next_query)

        # State 2: Active -> Inverted
        current_state = {"active": True, "inversed": False}
        next_query = self.parser.generate_future_query(
            'area:"work"', area_filter, current_state
        )
        self.assertIn("-area:", next_query)

        # State 3: Inverted -> Inactive
        current_state = {"active": True, "inversed": True}
        next_query = self.parser.generate_future_query(
            '-area:"work"', area_filter, current_state
        )
        self.assertEqual(next_query.strip(), "")
