from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from task_processor.constants import GTDStatus, Priority
from task_processor.models import Item
from task_processor.models.base_models import Area, Context
from task_processor.search import apply_search


class TestSearchFunctionality(TestCase):
    """Test the search functionality with real Item objects"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(username='testuser', email='test@example.com')

        # Create test areas and contexts
        self.work_area = Area.objects.create(name='Work', user=self.user)
        self.personal_area = Area.objects.create(name='Personal', user=self.user)

        self.office_context = Context.objects.create(name='office', user=self.user)
        self.home_context = Context.objects.create(name='home', user=self.user)

        # Create test items
        self.inbox_item = Item.objects.create(
            title="Process email",
            status=GTDStatus.INBOX,
            priority=Priority.NORMAL,
            user=self.user
        )

        self.next_action = Item.objects.create(
            title="Call client",
            status=GTDStatus.NEXT_ACTION,
            priority=Priority.HIGH,
            area=self.work_area,
            user=self.user
        )
        self.next_action.contexts.add(self.office_context)

        self.overdue_item = Item.objects.create(
            title="Overdue task",
            status=GTDStatus.NEXT_ACTION,
            due_date=timezone.now() - timedelta(days=2),
            priority=Priority.URGENT,
            user=self.user
        )

        self.project = Item.objects.create(
            title="Website redesign",
            status=GTDStatus.PROJECT,
            area=self.work_area,
            user=self.user
        )

        self.waiting_item = Item.objects.create(
            title="Waiting for approval",
            status=GTDStatus.WAITING_FOR,
            waiting_for_person="John Doe",
            user=self.user
        )

    def test_status_search(self):
        """Test searching by status using 'in:' filter"""
        # Test inbox search
        result = apply_search(Item.objects.for_user(self.user), "in:inbox")
        self.assertEqual(list(result), [self.inbox_item])

        # Test next action search
        result = apply_search(Item.objects.for_user(self.user), "in:next")
        self.assertIn(self.next_action, result)
        self.assertIn(self.overdue_item, result)

        # Test project search
        result = apply_search(Item.objects.for_user(self.user), "in:project")
        self.assertEqual(list(result), [self.project])

    def test_priority_search(self):
        """Test searching by priority"""
        # Test high priority
        result = apply_search(Item.objects.for_user(self.user), "priority:high")
        self.assertEqual(list(result), [self.next_action])

        # Test urgent priority
        result = apply_search(Item.objects.for_user(self.user), "priority:urgent")
        self.assertEqual(list(result), [self.overdue_item])

        # Test excluded priority
        result = apply_search(Item.objects.for_user(self.user), "-priority:normal")
        self.assertNotIn(self.inbox_item, result)

    def test_state_search(self):
        """Test searching by state using 'is:' filter"""
        # Test overdue items
        result = apply_search(Item.objects.for_user(self.user), "is:overdue")
        self.assertEqual(list(result), [self.overdue_item])

        # Test active items
        result = apply_search(Item.objects.for_user(self.user), "is:active")
        active_items = result.values_list('id', flat=True)
        # Should exclude completed/cancelled items
        self.assertIn(self.inbox_item.id, active_items)
        self.assertIn(self.next_action.id, active_items)

    def test_area_search(self):
        """Test searching by area"""
        result = apply_search(Item.objects.for_user(self.user), 'area:"Work"')
        work_items = list(result)
        self.assertIn(self.next_action, work_items)
        self.assertIn(self.project, work_items)
        self.assertNotIn(self.inbox_item, work_items)

    def test_context_search(self):
        """Test searching by context"""
        result = apply_search(Item.objects.for_user(self.user), 'context:"office"')
        self.assertEqual(list(result), [self.next_action])

    def test_waiting_search(self):
        """Test searching waiting for items"""
        result = apply_search(Item.objects.for_user(self.user), 'waiting:"John"')
        self.assertEqual(list(result), [self.waiting_item])

    def test_free_text_search(self):
        """Test free text search in title and description"""
        result = apply_search(Item.objects.for_user(self.user), "email")
        self.assertEqual(list(result), [self.inbox_item])

        result = apply_search(Item.objects.for_user(self.user), "redesign")
        self.assertEqual(list(result), [self.project])

    def test_combined_search(self):
        """Test combined search with multiple filters"""
        # Search for high priority items in work area
        result = apply_search(Item.objects.for_user(self.user), 'priority:high area:"Work"')
        self.assertEqual(list(result), [self.next_action])

        # Search with exclusion
        result = apply_search(Item.objects.for_user(self.user), 'in:next -priority:urgent')
        self.assertEqual(list(result), [self.next_action])

    def test_has_filters(self):
        """Test 'has:' existence filters"""
        # Test has area
        result = apply_search(Item.objects.for_user(self.user), "has:area")
        has_area_items = list(result)
        self.assertIn(self.next_action, has_area_items)
        self.assertIn(self.project, has_area_items)
        self.assertNotIn(self.inbox_item, has_area_items)

    def test_tags_alias(self):
        """Test that 'tags:' works as alias for 'context:'"""
        result1 = apply_search(Item.objects.for_user(self.user), 'context:"office"')
        result2 = apply_search(Item.objects.for_user(self.user), 'tags:"office"')
        self.assertEqual(list(result1), list(result2))

    def test_complex_query(self):
        """Test a complex query with multiple filters and free text"""
        # Create an item that matches complex criteria
        complex_item = Item.objects.create(
            title="Important office task",
            description="This is urgent work",
            status=GTDStatus.NEXT_ACTION,
            priority=Priority.HIGH,
            area=self.work_area,
            user=self.user
        )
        complex_item.contexts.add(self.office_context)

        # Search: high priority work items with "office" in title, excluding inbox
        result = apply_search(
            Item.objects.for_user(self.user),
            'priority:high area:"Work" -in:inbox office'
        )

        result_list = list(result)
        self.assertIn(complex_item, result_list)
        self.assertNotIn(self.inbox_item, result_list)