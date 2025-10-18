from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.http import JsonResponse
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

from .constants import GTDConfig, GTDStatus
from .forms import ItemForm
from .models import Area, Context, Item, Tag
from .search import FilterCategory


class ForceHtmxRequestMixin(object):
    def dispatch(self, request, *args, **kwargs):
        if request.method == "GET" and request.headers.get("HX-Request") != "true":
            return redirect(reverse_lazy("dashboard"))
        return super().dispatch(request, *args, **kwargs)


class ReturnRefererMixin(object):
    fallback_url = reverse_lazy("dashboard")

    def get_success_url(self):
        referer = self.request.META.get("HTTP_REFERER")
        if (
            referer
            and is_same_domain(referer, self.request.get_host())
            and referer != self.request.build_absolute_uri()
        ):
            return referer

        return self.get_return_url()

    def get_return_url(self):
        return self.request.GET.get("returnUrl", self.fallback_url)


@method_decorator(login_required, name="dispatch")
class DashboardStatsView(TemplateView):
    template_name = "stats/stats.html"
    """
    HTMX endpoint for dashboard charts section.
    """

    def get_context_data(self, **kwargs):
        user_items = Item.objects.for_user(self.request.user)

        # Recent activity (last 7 days)
        week_ago = timezone.now() - timedelta(days=7)

        return {
            **self._get_statistic_count(),
            "completed_count": Item.objects.for_user(self.request.user)
            .filter(is_completed=True)
            .count(),
            "priority_stats": user_items.filter(is_completed=False)
            .values("priority")
            .annotate(count=Count("id"))
            .order_by("-priority"),
            "recent_activity": {
                "completed_this_week": user_items.filter(
                    completed_at__gte=week_ago
                ).count(),
                "created_this_week": user_items.filter(
                    created_at__gte=week_ago
                ).count(),
                "someday_maybe_count": Item.objects.someday_maybe(
                    self.request.user
                ).count(),
            },
            "recent_items": user_items.order_by("-updated_at")[:10],
        }

    def _get_statistic_count(self):
        result = (
            Item.objects.filter(user=self.request.user)
            .values("status")
            .annotate(total=Count("id"))
        )

        return {
            f"status_{result[status]}": result[status]["total"]
            for status in range(len(result))
        }


class LoginView(View):
    """
    Custom login view for GTD application.
    """

    def get(self, request):
        """Display login form"""
        if request.user.is_authenticated:
            return redirect("dashboard")

        context = {}
        if settings.IS_DEMO:
            context["demo_users"] = (
                {"username": "user1", "password": "password"},
                {"username": "user2", "password": "password"},
            )

        return render(request, "auth/login.html", context)

    def post(self, request):
        """Handle login form submission"""
        username = request.POST.get("username")
        password = request.POST.get("password")

        if username and password:
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(
                    request, f"Welcome back, {user.first_name or user.username}!"
                )

                # Redirect to next parameter if provided, otherwise dashboard
                next_url = request.GET.get("next") or request.POST.get("next")
                return redirect(next_url if next_url else "dashboard")
            else:
                messages.error(request, "Invalid username or password.")
        else:
            messages.error(request, "Please provide both username and password.")

        return render(request, "auth/login.html")


class LogoutView(View):
    """
    Custom logout view for GTD application.
    """

    def get(self, request):
        """Handle logout"""
        if request.user.is_authenticated:
            username = request.user.first_name or request.user.username
            logout(request)
            messages.success(request, f"Goodbye, {username}! You have been logged out.")
        return redirect("login")

    def post(self, request):
        """Handle logout via POST"""
        return self.get(request)


@method_decorator(login_required, name="dispatch")
class DashboardView(ListView):
    template_name = "dashboard/dashboard.html"
    paginate_by = 50
    page_kwarg = "page"

    def get_page(self):
        return (
            self.kwargs.get(self.page_kwarg)
            or self.request.GET.get(self.page_kwarg)
            or 1
        )

    def get_search_query(self):
        return self.request.GET.get("q", "in:next in:-completed in:-cancelled").strip()

    """
    Dashboard view with real-time statistics and insights.
    """

    def get_queryset(self):
        from django.db import models as django_models
        from django.db.models.functions import Cast

        today = timezone.now().date()
        items = (
            Item.objects.for_user(self.request.user)
            .select_related("area")
            .prefetch_related("contexts")
            .prefetch_related("tags")
            .prefetch_related("parent")
            .annotate(
                status_order=Case(
                    When(
                        status__in=[
                            GTDStatus.COMPLETED.value,
                            GTDStatus.COMPLETED.value,
                        ],
                        then=Value(-5),
                    ),
                    When(status__in=[GTDStatus.CANCELLED.value], then=Value(-10)),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
                parent_order=Case(
                    When(parent__pk__isnull=True, then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
                can_start=Case(
                    When(
                        Q(start_date=None) | Q(start_date__lte=timezone.now()),
                        then=Value(-5),
                    ),
                    default=Value(-10),
                    output_field=IntegerField(),
                ),
                due_date_boost=Case(
                    # Overdue items (negative days) get maximum boost
                    When(due_date__lt=today, then=Value(1000)),
                    # Due today gets very high boost
                    When(due_date=today, then=Value(100)),
                    # Due tomorrow
                    When(
                        due_date=Cast(
                            Value(today) + timedelta(days=1),
                            output_field=django_models.DateField(),
                        ),
                        then=Value(50),
                    ),
                    # Due in 2 days
                    When(
                        due_date=Cast(
                            Value(today) + timedelta(days=2),
                            output_field=django_models.DateField(),
                        ),
                        then=Value(25),
                    ),
                    # Due in 3 days
                    When(
                        due_date=Cast(
                            Value(today) + timedelta(days=3),
                            output_field=django_models.DateField(),
                        ),
                        then=Value(12),
                    ),
                    # Due in 4-7 days
                    When(
                        Q(
                            due_date__gte=Cast(
                                Value(today) + timedelta(days=4),
                                output_field=django_models.DateField(),
                            )
                        )
                        & Q(
                            due_date__lte=Cast(
                                Value(today) + timedelta(days=7),
                                output_field=django_models.DateField(),
                            )
                        ),
                        then=Value(5),
                    ),
                    # No due date or far future
                    default=Value(0),
                    output_field=IntegerField(),
                ),
            )
            .order_by(
                "-parent_order",
                "-status_order",
                "-due_date_boost",
                "-can_start",
                "-priority",
                "-created_at",
            )
        )

        from .search import apply_search

        return apply_search(items, self.get_search_query())

    def get_context_data(self, *, object_list=None, **kwargs):
        # Get recent areas and contexts for filter suggestions
        areas = Area.objects.filter(user=self.request.user).order_by("-created_at")
        contexts = Context.objects.filter(user=self.request.user).order_by(
            "-created_at"
        )

        # Create search filter instance
        from .search import SearchFilter

        search_filter = SearchFilter(
            user=self.request.user,
            areas=areas,
            contexts=contexts,
            projects=Item.objects.projects(self.request.user),
        )

        context = super().get_context_data(object_list=object_list, **kwargs)

        context.update(
            {
                "stats": {**self._get_statistic_count()},
                "areas": areas,
                "contexts": contexts,
                "search_query": self.get_search_query(),
                "search_filters": search_filter.get_filters_with_state(
                    self.get_search_query()
                ),
                "filter_categories": [
                    {"value": category.value, "label": category.label}
                    for category in FilterCategory
                ],
                "now": timezone.now(),
            }
        )
        return context

    def _get_statistic_count(self):
        result = (
            Item.objects.for_user(self.request.user)
            .values("status")
            .annotate(total=Count("id"))
        )
        return {f"count_status_{r['status']}": r["total"] for r in result}


@method_decorator(login_required, name="dispatch")
class StatsView(View):
    """
    Dashboard view with real-time statistics and insights.
    """

    def get(self, request):
        # Get the Item model
        Item = get_model("task_processor", "Item")

        # Get current user's items
        user_items = Item.objects.for_user(request.user)

        # Calculate statistics
        stats = {
            "inbox_count": Item.objects.inbox_items(request.user).count(),
            "next_actions_count": Item.objects.next_actions(request.user).count(),
            "projects_count": Item.objects.projects(request.user).count(),
            "waiting_for_count": Item.objects.waiting_for(request.user).count(),
            "someday_maybe_count": Item.objects.someday_maybe(request.user).count(),
            "completed_count": user_items.filter(is_completed=True).count(),
        }

        # Calculate priority distribution
        priority_stats = (
            user_items.filter(is_completed=False)
            .values("priority")
            .annotate(count=Count("id"))
            .order_by("-priority")
        )

        # Get urgent items (overdue and due today)
        urgent_items = {
            "overdue": Item.objects.overdue(request.user)[:5],
            "due_today": Item.objects.due_today(request.user)[:5],
            "follow_ups": Item.objects.waiting_for(request.user, needs_follow_up=True)[
                :5
            ],
        }

        # Recent activity (last 7 days)
        week_ago = timezone.now() - timedelta(days=7)
        recent_activity = {
            "completed_this_week": user_items.filter(
                completed_at__gte=week_ago
            ).count(),
            "created_this_week": user_items.filter(created_at__gte=week_ago).count(),
        }

        # Get recent items for the activity feed
        recent_items = user_items.order_by("-updated_at")[:10]

        context = {
            "stats": stats,
            "priority_stats": priority_stats,
            "urgent_items": urgent_items,
            "recent_activity": recent_activity,
            "recent_items": recent_items,
        }

        return render(request, "task_processor/stats/stats.html", context)


@method_decorator(login_required, name="dispatch")
class ItemTransitionView(FormView):
    """
    Handle item state transitions for logged-in users.
    Supports form-based transitions for decorated methods.
    """

    template_name = "transitions/form.html"

    def get_form_class(self):
        return self.transition.form_class

    def dispatch(self, request, *args, **kwargs):
        """Initialize transition data and validate availability"""
        # Extract URL parameters
        self.item_id = kwargs.get("item_id")
        self.transition_slug = kwargs.get("transition_slug")

        # Get item and validate ownership
        Item = get_model("task_processor", "Item")
        self.item = get_object_or_404(Item, id=self.item_id, user=request.user)

        # Get transition and validate availability
        available_transitions = self.item.get_available_transitions()
        self.transition = available_transitions.get_transition(self.transition_slug)

        if not self.transition:
            messages.error(
                request,
                f"Transition '{self.transition_slug}' is not available for this item.",
            )
            return redirect(self.get_success_url())

        # If no form required, execute transition directly
        if not self.get_form_class():
            self._execute_transition()
            return redirect(self.get_success_url())

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        """Add transition and item data to template context"""
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "item": self.item,
                "transition": self.transition,
                "return_url": self.get_success_url(),
            }
        )
        return context

    def get_success_url(self):
        """Get the URL to redirect to after successful transition"""
        return self.request.GET.get("returnUrl", reverse("dashboard"))

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
                f"Successfully applied '{self.transition.label}' to '{self.item.title}'.",
            )
        except Exception as e:
            messages.error(self.request, f"Error applying transition: {str(e)}")


@method_decorator(login_required, name="dispatch")
@method_decorator(csrf_exempt, name="dispatch")
class ItemDetailView(ForceHtmxRequestMixin, UpdateView):
    """
    View for displaying item details in a modal.
    """

    model = Item
    pk_url_kwarg = "item_id"
    template_name = "partials/item_detail_modal.html"
    form_class = ItemForm
    context_object_name = "item"

    def get_form_kwargs(self):
        return {
            "item_flow": self.object.flow,
            "user": self.request.user,
            **super().get_form_kwargs(),
        }

    def form_valid(self, form):
        self.object = form.save()
        # Return the updated modal content after successful save
        return self.render_to_response(self.get_context_data())

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form), status=400)

    def get_queryset(self):
        return Item.objects.for_user(self.request.user)


@method_decorator(login_required, name="dispatch")
class ItemCreateView(ReturnRefererMixin, CreateView):
    """
    View for creating new GTD items.
    """

    model = Item
    form_class = ItemForm
    template_name = "items/item_form.html"

    def get_form_kwargs(self):
        # Create a new item instance for the form
        new_item = Item(user=self.request.user)
        return {
            "item_flow": new_item.flow,
            "user": self.request.user,
            "instance": new_item,
            **super().get_form_kwargs(),
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Create New Item"

        # Add empty initial values for autocomplete fields (for consistency)
        context.update(
            {
                "tags_initial_values": "",
                "contexts_initial_values": "",
                "area_initial_values": "",
                "parent_initial_values": "",
            }
        )

        return context

    def form_valid(self, form):
        form.instance.user = self.request.user
        return_url = super().form_valid(form)
        messages.success(
            self.request, f"Item '{self.object.title}' created successfully!"
        )
        return return_url


@method_decorator(login_required, name="dispatch")
class ItemUpdateView(ReturnRefererMixin, UpdateView):
    """
    View for updating existing GTD items.
    """

    pk_url_kwarg = "item_id"
    model = Item
    form_class = ItemForm
    template_name = "items/item_form.html"

    def get_form_class(self):
        return self.form_class

    def get_form_kwargs(self):
        return {
            "item_flow": self.object.flow,
            "user": self.request.user,
            **super().get_form_kwargs(),
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = f'Update "{self.object.title}"'

        # Add initial values for autocomplete fields
        form = context.get("form")
        if form and hasattr(form, "get_initial_values_for_field"):
            context.update(
                {
                    "tags_initial_values": form.get_initial_values_for_field("tags"),
                    "contexts_initial_values": form.get_initial_values_for_field(
                        "contexts"
                    ),
                    "area_initial_values": form.get_initial_values_for_field("area"),
                    "parent_initial_values": form.get_initial_values_for_field(
                        "parent"
                    ),
                }
            )

        return context

    def form_valid(self, form):
        super().form_valid(form)
        messages.success(
            self.request, f"Item '{self.object.title}' updated successfully!"
        )
        return redirect("dashboard")


class AutocompleteView(View):
    """
    API endpoint for autocomplete functionality.
    Supports tags, areas, contexts, and parent projects based on field_type.
    """

    # Field type configuration mapping
    FIELD_CONFIG = {
        "tags": {
            "model": Tag,
            "search_field": "name",
            "display_field": "name",
            "order_field": "created_at",
            "format_result": lambda item: {"id": item.id, "text": item.name},
        },
        "areas": {
            "model": Area,
            "search_field": "name",
            "display_field": "name",
            "order_field": "created_at",
            "format_result": lambda item: {"id": item.id, "text": item.name},
        },
        "contexts": {
            "model": Context,
            "search_field": "name",
            "display_field": "name",
            "order_field": "created_at",
            "format_result": lambda item: {"id": item.id, "text": item.name},
        },
        "parent": {
            "model": Item,
            "search_field": "title",
            "display_field": "title",
            "order_field": "updated_at",
            "format_result": lambda item: {
                "id": item.id,
                "text": f"{item.title} ({item.get_status_display()})",
            },
            "extra_filters": {
                "status__in": GTDConfig.STATUS_WITH_PARENT_ALLOWED,
                "parent__isnull": True,
            },
        },
    }

    def get(self, request, field_type):
        try:
            # Check authentication
            if not request.user.is_authenticated:
                return JsonResponse({"error": "Authentication required"}, status=401)

            query = request.GET.get("q", "").strip()
            ids_param = request.GET.get("ids", "").strip()

            # Check if field_type is supported
            if field_type not in self.FIELD_CONFIG:
                return JsonResponse(
                    {"error": f"Unsupported field type: {field_type}"}, status=400
                )

            config = self.FIELD_CONFIG[field_type]
            model = config["model"]
            search_field = config["search_field"]
            order_field = config["order_field"]
            format_result = config["format_result"]

            # Build base queryset
            queryset = model.objects.filter(user=request.user)

            # Apply extra filters if specified
            if "extra_filters" in config:
                queryset = queryset.filter(**config["extra_filters"])

            # Handle specific IDs request (for loading selected items)
            if ids_param:
                try:
                    ids = [
                        int(id.strip())
                        for id in ids_param.split(",")
                        if id.strip().isdigit()
                    ]
                    if ids:
                        queryset = queryset.filter(id__in=ids)
                    else:
                        queryset = queryset.none()
                except ValueError:
                    queryset = queryset.none()
            # Apply search query if provided
            elif len(query) > 0:
                # For better search results, prioritize items that start with the query
                # and include items that contain the query anywhere
                from django.db.models import Case, IntegerField, Value, When

                search_filter = {f"{search_field}__icontains": query}
                queryset = (
                    queryset.filter(**search_filter)
                    .annotate(
                        search_priority=Case(
                            When(
                                **{f"{search_field}__istartswith": query}, then=Value(1)
                            ),
                            When(
                                **{f"{search_field}__icontains": query}, then=Value(2)
                            ),
                            default=Value(3),
                            output_field=IntegerField(),
                        )
                    )
                    .order_by("search_priority", search_field)
                )
            else:
                # When no query, show recent items first
                queryset = queryset.order_by(f"-{order_field}")

            # Handle special case for parent field - exclude current item
            if field_type == "parent":
                item_id = request.GET.get("item_id")
                if item_id:
                    queryset = queryset.exclude(id=item_id)

            # Get results and format them (more results for better search experience)
            limit = 15 if query else 10  # Show more results when searching
            items = queryset[:limit]
            results = [format_result(item) for item in items]

            return JsonResponse({"results": results})

        except Exception as e:
            # Log the error and return a proper JSON error response
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Autocomplete error for {field_type}: {str(e)}")
            return JsonResponse(
                {"error": f"Internal server error: {str(e)}"}, status=500
            )


@method_decorator(login_required, name="dispatch")
@method_decorator(csrf_exempt, name="dispatch")
class CreateFieldView(View):
    """
    API endpoint for creating new field values on the fly.
    Supports tags, areas, and contexts based on field_type.
    """

    def post(self, request, field_type):
        try:
            import json

            data = json.loads(request.body)
            field_name = data.get("name", "").strip()

            if not field_name:
                return JsonResponse(
                    {"error": f"{field_type.capitalize()} name is required"}, status=400
                )

            new_item = None

            if field_type == "tags":
                existing_item = Tag.objects.filter(
                    user=request.user, name=field_name
                ).first()
                if not existing_item:
                    new_item = Tag.objects.create(user=request.user, name=field_name)

            elif field_type == "areas":
                existing_item = Area.objects.filter(
                    user=request.user, name=field_name
                ).first()
                if not existing_item:
                    new_item = Area.objects.create(user=request.user, name=field_name)

            elif field_type == "contexts":
                existing_item = Context.objects.filter(
                    user=request.user, name=field_name
                ).first()
                if not existing_item:
                    new_item = Context.objects.create(
                        user=request.user, name=field_name
                    )

            else:
                return JsonResponse(
                    {"error": f"Unsupported field type: {field_type}"}, status=400
                )

            # Return existing or new item
            item = existing_item or new_item
            return JsonResponse({"id": item.id, "text": item.name})

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
