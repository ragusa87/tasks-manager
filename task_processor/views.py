from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.http import is_same_domain
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import (
    CreateView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)
from factory.django import get_model

from .forms import ItemCreateForm, ItemDetailForm, ItemUpdateForm, ItemUpdateProjectForm
from .models import Area, Context, Item


class ForceHtmxRequestMixin(object):
    def dispatch(self, request, *args, **kwargs):
        if request.method == "GET" and request.headers.get("HX-Request") != "true":
            return redirect(reverse_lazy('dashboard'))
        return super().dispatch(request, *args, **kwargs)

class ReturnRefererMixin(object):
    fallback_url = reverse_lazy('dashboard')
    def get_success_url(self):
        referer = self.request.META.get('HTTP_REFERER')
        if referer and is_same_domain(referer, self.request.get_host()) and referer != self.request.build_absolute_uri():
            return referer

        return self.get_return_url()

    def get_return_url(self):
        return self.request.GET.get('returnUrl', self.fallback_url)

@method_decorator(login_required, name='dispatch')
class DashboardStatsView(TemplateView):
    template_name = 'stats/stats.html'
    """
    HTMX endpoint for dashboard charts section.
    """

    def get_context_data(self, **kwargs):
        user_items = Item.objects.for_user(self.request.user)

        # Recent activity (last 7 days)
        week_ago = timezone.now() - timedelta(days=7)

        return {
            **self._get_statistic_count(),
            'completed_count': Item.objects.for_user(self.request.user).filter(is_completed=True).count(),
            'priority_stats': user_items.filter(is_completed=False).values('priority').annotate(
                count=Count('id')
            ).order_by('-priority'),
            'recent_activity': {
                'completed_this_week': user_items.filter(completed_at__gte=week_ago).count(),
                'created_this_week': user_items.filter(created_at__gte=week_ago).count(),
                'someday_maybe_count': Item.objects.someday_maybe(self.request.user).count(),
            },
            'recent_items': user_items.order_by('-updated_at')[:10],
        }

    def _get_statistic_count(self):
        result = Item.objects.filter(user=self.request.user).values('status').annotate(total=Count('id'))

        return {f"status_{result[status]}": result[status]['total'] for status in range(len(result))}



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
class DashboardView(ListView):
    template_name = 'dashboard/dashboard.html'
    paginate_by = 50
    page_kwarg = "page"

    def get_page(self):
        return self.kwargs.get(self.page_kwarg) or self.request.GET.get(self.page_kwarg) or 1

    def get_search_query(self):
        return self.request.GET.get("q",'in:next in:-completed in:-cancelled').strip()
    """
    Dashboard view with real-time statistics and insights.
    """
    def get_queryset(self):
        items = Item.objects.for_user(self.request.user).select_related('area').prefetch_related('contexts').prefetch_related('tags').prefetch_related('parent_project')

        from .search import apply_search
        return apply_search(items, self.get_search_query())


    def get_context_data(self, *, object_list=None, **kwargs):
        # Get recent areas and contexts for filter suggestions
        areas = Area.objects.filter(user=self.request.user).order_by('-created_at')
        contexts = Context.objects.filter(user=self.request.user).order_by('-created_at')
        context = super().get_context_data(object_list=object_list, **kwargs)
        context.update({
            "stats": {
                **self._get_statistic_count()
            },
            'areas': areas,
            'contexts': contexts,
            'search_query': self.get_search_query(),
            'now': timezone.now(),
        })
        return context

    def _get_statistic_count(self):
        result = Item.objects.for_user(self.request.user).values('status').annotate(total=Count('id'))
        return {f"count_status_{r['status']}": r['total'] for r in result}

@method_decorator(login_required, name='dispatch')
class StatsView(View):
    """
    Dashboard view with real-time statistics and insights.
    """

    def get(self, request):
        # Get the Item model
        Item = get_model('task_processor', 'Item')

        # Get current user's items
        user_items = Item.objects.for_user(request.user)

        # Calculate statistics
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
        }

        return render(request, 'task_processor/stats/stats.html', context)


@method_decorator(login_required, name='dispatch')
class ItemTransitionView(FormView):
    """
    Handle item state transitions for logged-in users.
    Supports form-based transitions for decorated methods.
    """
    template_name = 'transitions/form.html'

    def get_form_class(self):
        return self.transition.form_class

    def dispatch(self, request, *args, **kwargs):
        """Initialize transition data and validate availability"""
        # Extract URL parameters
        self.item_id = kwargs.get('item_id')
        self.transition_slug = kwargs.get('transition_slug')

        # Get item and validate ownership
        Item = get_model('task_processor', 'Item')
        self.item = get_object_or_404(Item, id=self.item_id, user=request.user)

        # Get transition and validate availability
        available_transitions = self.item.get_available_transitions()
        self.transition = available_transitions.get_transition(self.transition_slug)

        if not self.transition:
            messages.error(request, f"Transition '{self.transition_slug}' is not available for this item.")
            return redirect(self.get_success_url())

        # If no form required, execute transition directly
        if not self.get_form_class():
            self._execute_transition()
            return redirect(self.get_success_url())

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        """Add transition and item data to template context"""
        context = super().get_context_data(**kwargs)
        context.update({
            'item': self.item,
            'transition': self.transition,
            'return_url': self.get_success_url()
        })
        return context

    def get_success_url(self):
        """Get the URL to redirect to after successful transition"""
        return self.request.GET.get('returnUrl', reverse('dashboard'))

    def form_valid(self, form):
        """Handle valid form submission - execute transition with form data"""
        self._execute_transition(**form.cleaned_data if form is not None else {})

        return super().form_valid(form)

    def _execute_transition(self, **kwargs):
        """Execute transition without form (for direct transitions)"""
        try:
            method = getattr(self.item.flow, self.transition.name)
            method(**kwargs)
            self.item.save()
            messages.success(
                self.request,
                f"Successfully applied '{self.transition.label}' to '{self.item.title}'."
            )
        except Exception as e:
            messages.error(self.request, f"Error applying transition: {str(e)}")



@method_decorator(login_required, name='dispatch')
@method_decorator(csrf_exempt, name='dispatch')
class ItemDetailView(ForceHtmxRequestMixin, UpdateView):
    """
    View for displaying item details in a modal.
    """
    model = Item
    pk_url_kwarg = "item_id"
    template_name = "partials/item_detail_modal.html"
    form_class = ItemDetailForm
    context_object_name = "item"

    def get_form_kwargs(self):
        return {
            'item_flow': self.object.flow,
            'user': self.request.user,
            **super().get_form_kwargs(),
        }

    def form_valid(self, form):
        self.object = form.save()
        # Return the updated modal content after successful save
        return self.render_to_response(self.get_context_data())

    def get_queryset(self):
        return Item.objects.for_user(self.request.user)


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

    def get_form_class(self):
        if self.object and self.object.is_project:
            return ItemUpdateProjectForm
        return self.form_class

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

