from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.http import is_same_domain
from django.views.generic import CreateView, UpdateView, View
from factory.django import get_model

from .forms import ItemCreateForm, ItemUpdateForm
from .models import Item


class ReturnRefererMixin(View):
    fallback_url = reverse_lazy('dashboard')
    def get_success_url(self):
        referer = self.request.META.get('HTTP_REFERER')
        if referer and is_same_domain(referer, self.request.get_host()) and referer != self.request.build_absolute_uri():
            return referer

        return self.get_return_url()

    def get_return_url(self):
        return self.request.GET.get('returnUrl', self.fallback_url)

@method_decorator(login_required, name='dispatch')
class DashboardStatsView(View):
    """
    HTMX endpoint for dashboard statistics cards.
    """

    def get(self, request):
        Item = get_model('task_processor', 'Item')

        stats = {
            'inbox_count': Item.objects.inbox_items(request.user).count(),
            'next_actions_count': Item.objects.next_actions(request.user).count(),
            'projects_count': Item.objects.projects(request.user).count(),
            'waiting_for_count': Item.objects.waiting_for(request.user).count(),
            'someday_maybe_count': Item.objects.someday_maybe(request.user).count(),
            'completed_count': Item.objects.for_user(request.user).filter(is_completed=True).count(),
        }

        return render(request, 'partials/stats_cards.html', {'stats': stats})


@method_decorator(login_required, name='dispatch')
class DashboardChartsView(View):
    """
    HTMX endpoint for dashboard charts section.
    """

    def get(self, request):
        Item = get_model('task_processor', 'Item')
        user_items = Item.objects.for_user(request.user)

        # Calculate priority distribution
        priority_stats = user_items.filter(is_completed=False).values('priority').annotate(
            count=Count('id')
        ).order_by('-priority')

        # Recent activity (last 7 days)
        week_ago = timezone.now() - timedelta(days=7)
        recent_activity = {
            'completed_this_week': user_items.filter(completed_at__gte=week_ago).count(),
            'created_this_week': user_items.filter(created_at__gte=week_ago).count(),
        }

        stats = {
            'someday_maybe_count': Item.objects.someday_maybe(request.user).count(),
        }

        context = {
            'priority_stats': priority_stats,
            'recent_activity': recent_activity,
            'stats': stats,
        }

        return render(request, 'partials/charts_section.html', context)


@method_decorator(login_required, name='dispatch')
class DashboardUrgentView(View):
    """
    HTMX endpoint for urgent items section.
    """

    def get(self, request):
        Item = get_model('task_processor', 'Item')

        urgent_items = {
            'overdue': Item.objects.overdue(request.user)[:5],
            'due_today': Item.objects.due_today(request.user)[:5],
            'follow_ups': Item.objects.waiting_for(request.user, needs_follow_up=True)[:5],
        }

        return render(request, 'partials/urgent_items.html', {'urgent_items': urgent_items})


@method_decorator(login_required, name='dispatch')
class DashboardActivityView(View):
    """
    HTMX endpoint for recent activity section.
    """

    def get(self, request):
        Item = get_model('task_processor', 'Item')
        user_items = Item.objects.for_user(request.user)

        recent_items = user_items.order_by('-updated_at')[:10]

        return render(request, 'partials/recent_activity.html', {'recent_items': recent_items})


class LoginView(View):
    """
    Custom login view for GTD application.
    """

    def get(self, request):
        """Display login form"""
        if request.user.is_authenticated:
            return redirect('dashboard')

        context = {}
        if settings.IS_DEMO:
            context['demo_users'] = (
                {'username': 'user1', 'password': 'password'},
                {'username': 'user2', 'password': 'password'},
            )

        return render(request, 'auth/login.html', context)

    def post(self, request):
        """Handle login form submission"""
        username = request.POST.get('username')
        password = request.POST.get('password')

        if username and password:
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {user.first_name or user.username}!')

                # Redirect to next parameter if provided, otherwise dashboard
                next_url = request.GET.get('next') or request.POST.get('next')
                return redirect(next_url if next_url else 'dashboard')
            else:
                messages.error(request, 'Invalid username or password.')
        else:
            messages.error(request, 'Please provide both username and password.')

        return render(request, 'auth/login.html')


class LogoutView(View):
    """
    Custom logout view for GTD application.
    """

    def get(self, request):
        """Handle logout"""
        if request.user.is_authenticated:
            username = request.user.first_name or request.user.username
            logout(request)
            messages.success(request, f'Goodbye, {username}! You have been logged out.')
        return redirect('login')

    def post(self, request):
        """Handle logout via POST"""
        return self.get(request)


@method_decorator(login_required, name='dispatch')
class DashboardView(View):
    """
    GTD Dashboard view with real-time statistics and insights.
    """

    def get(self, request):
        # Get the Item model
        Item = get_model('task_processor', 'Item')

        # Get current user's items
        user_items = Item.objects.for_user(request.user)

        # Calculate GTD statistics
        stats = {
            'inbox_count': Item.objects.inbox_items(request.user).count(),
            'next_actions_count': Item.objects.next_actions(request.user).count(),
            'projects_count': Item.objects.projects(request.user).count(),
            'waiting_for_count': Item.objects.waiting_for(request.user).count(),
            'someday_maybe_count': Item.objects.someday_maybe(request.user).count(),
            'completed_count': user_items.filter(is_completed=True).count(),
        }

        # Calculate priority distribution
        priority_stats = user_items.filter(is_completed=False).values('priority').annotate(
            count=Count('id')
        ).order_by('-priority')

        # Get urgent items (overdue and due today)
        urgent_items = {
            'overdue': Item.objects.overdue(request.user)[:5],
            'due_today': Item.objects.due_today(request.user)[:5],
            'follow_ups': Item.objects.waiting_for(request.user, needs_follow_up=True)[:5],
        }

        # Recent activity (last 7 days)
        week_ago = timezone.now() - timedelta(days=7)
        recent_activity = {
            'completed_this_week': user_items.filter(
                completed_at__gte=week_ago
            ).count(),
            'created_this_week': user_items.filter(
                created_at__gte=week_ago
            ).count(),
        }

        # Get recent items for the activity feed
        recent_items = user_items.order_by('-updated_at')[:10]

        context = {
            'stats': stats,
            'priority_stats': priority_stats,
            'urgent_items': urgent_items,
            'recent_activity': recent_activity,
            'recent_items': recent_items,
            'now': timezone.now(),
        }

        return render(request, 'dashboard.html', context)


@method_decorator(login_required, name='dispatch')
class InboxView(View):
    """
    Inbox view for unprocessed GTD items with pagination.
    """

    def get(self, request):
        Item = get_model('task_processor', 'Item')

        # Get all inbox items for the current user
        inbox_items = Item.objects.inbox_items(request.user).order_by('-created_at')

        # Paginate the inbox items
        paginator = Paginator(inbox_items, 20)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        context = {
            'inbox_items': page_obj,
            'inbox_count': inbox_items.count(),
            'page_obj': page_obj,
            'paginator': paginator,
        }

        return render(request, 'inbox.html', context)


@method_decorator(login_required, name='dispatch')
class ItemTransitionView(View):
    """
    Handle item state transitions for logged-in users.
    """

    def get(self, request, item_id, transition_slug):
        Item = get_model('task_processor', 'Item')
        fallback_url = reverse('dashboard')
        # Get the item and ensure it belongs to the current user
        item = get_object_or_404(Item, id=item_id, user=request.user)

        # Get available transitions for this item
        available_transitions = item.get_available_transitions()

        # Check if the requested transition is allowed
        transition = None
        for trans in available_transitions:
            if trans.name == transition_slug:
                transition = trans
                break

        if not transition:
            messages.error(request, f"Transition '{transition_slug}' is not available for this item.")
            return_url = request.GET.get('returnUrl', fallback_url)
            return redirect(return_url)

        try:
            # Apply the transition using match statement for transitions that need args
            match transition_slug:
                # Add specific cases here for transitions that need arguments
                # case 'transition_with_args':
                #     # Handle transitions that need special arguments
                #     method = getattr(item, transition_slug)
                #     method(special_arg=value)
                case _:
                    # Default case: call the transition method without arguments
                    method = getattr(item.flow, transition_slug)
                    method()

            # Save the item after transition
            item.save()

            messages.success(request, f"Successfully applied '{transition.label}' to '{item.title}'.")

        except Exception as e:
            messages.error(request, f"Error applying transition: {str(e)}")

        # Redirect to the return URL or dashboard
        return_url = request.GET.get('returnUrl', fallback_url)
        return redirect(return_url)


@method_decorator(login_required, name='dispatch')
class ItemCreateView(ReturnRefererMixin, CreateView):
    """
    View for creating new GTD items.
    """
    model = Item
    form_class = ItemCreateForm
    template_name = "items/item_form.html"

    def get_form_kwargs(self):
        # Create a new item instance for the form
        new_item = Item(user=self.request.user)
        return {
            'item_flow': new_item.flow,
            'user': self.request.user,
            "instance": new_item,
            **super().get_form_kwargs(),
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Create New Item'
        return context

    def form_valid(self, form):
        form.instance.user = self.request.user
        return_url = super().form_valid(form)
        messages.success(self.request, f"Item '{self.object.title}' created successfully!")
        return return_url


@method_decorator(login_required, name='dispatch')
class ItemUpdateView(ReturnRefererMixin, UpdateView):
    """
    View for updating existing GTD items.
    """
    pk_url_kwarg = "item_id"
    model = Item
    form_class = ItemUpdateForm
    template_name = "items/item_form.html"
    def get_form_kwargs(self):
        return {
            'item_flow': self.object.flow,
            'user': self.request.user,
            **super().get_form_kwargs(),
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'Update "{self.object.title}"'
        return context

    def form_valid(self, form):
        super().form_valid(form)
        messages.success(self.request, f"Item '{self.object.title}' updated successfully!")
        return redirect('dashboard')

