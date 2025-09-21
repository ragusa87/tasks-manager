from django.contrib.auth.models import User
from django.test import TestCase

from task_processor.models.item import Item


class TestDecoratorDetection(TestCase):
    """Test decorator detection for form-based transitions"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(username='testuser', email='test@example.com')
        self.item = Item.objects.create(title="Test Item", user=self.user)

    def test_non_form_transitions_have_form_class(self):
        """Test that non-decorated transitions don't have form_class"""
        flow = self.item.flow

        # Get all available transitions
        available_transitions = flow.get_available_transitions()

        # Check transitions that should have forms
        form_transitions = ['delegate']

        for transition in available_transitions:
            if transition.name in form_transitions:
                form_class = getattr(transition, 'form_class', None)
                assert form_class is not None, f"{transition.name} should have a form_class"

    def test_non_form_transitions_have_no_form_class(self):
        """Test that non-decorated transitions don't have form_class"""
        flow = self.item.flow

        # Get all available transitions
        available_transitions = flow.get_available_transitions()

        # Check transitions that shouldn't have forms
        non_form_transitions = ['process_as_action', 'complete', 'process_as_someday_maybe']

        for transition in available_transitions:
            if transition.name in non_form_transitions:
                form_class = getattr(transition, 'form_class', None)
                assert form_class is None, f"{transition.name} should not have a form_class"


    def test_cancel_action_is_last(self):
        """Test that the cancel action appears last in the transition list due to its negative priority"""
        flow = self.item.flow

        # Get all available transitions
        available_transitions = flow.get_available_transitions()

        # Assert cancel transition is the last one in the list
        self.assertTrue(len(available_transitions) > 1, 'Should have at least one transition')
        last_transition = available_transitions[-1]
        self.assertEqual(last_transition.name, 'cancel',"Cancel transition should be the last transition in the list")
