import logging
from datetime import timedelta

import boto3
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.http import (
    FileResponse,
    Http404,
    HttpResponse,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.http import is_same_domain, url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import (
    CreateView,
    DeleteView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)
from factory.django import get_model

from .batch import (
    AreaBatchActions,
    ContextBatchActions,
    ItemBatchActions,
    TagBatchActions,
    get_batch_actions_class,
)
from .constants import GTDConfig, GTDStatus
from .forms import (
    AllowedSenderForm,
    AreaForm,
    ContextForm,
    EmailInboxForm,
    ItemForm,
    TagForm,
)
from .models import AllowedSender, Area, Context, Document, EmailInbox, Item, Tag
from .models.email_inbox import EMAIL_INBOX_PERMISSION
from .search import FilterCategory
from .uploads import DocumentValidationError, attach_document

logger = logging.getLogger(__name__)


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
        # returnUrl is caller-controlled: without validation it is an open
        # redirect (and a javascript: URL when rendered into an href).
        url = self.request.GET.get("returnUrl")
        if url and url_has_allowed_host_and_scheme(
            url,
            allowed_hosts={self.request.get_host()},
            require_https=self.request.is_secure(),
        ):
            return url
        return self.fallback_url


class HtmxModalActionMixin(ReturnRefererMixin):
    """Modal actions launched from the item list (transitions, delete).

    HTMX requests answer with an empty main body (clears #modal-container,
    closing the modal), an OOB flash-messages swap and an HX-Trigger that
    refreshes the list in place; plain requests redirect to a validated
    returnUrl.
    """

    def _is_htmx(self):
        return self.request.headers.get("HX-Request") == "true"

    def _htmx_refresh_response(self):
        response = render(self.request, "partials/_messages_oob.html")
        response["HX-Trigger"] = "refreshItems"
        return response

    def get_success_url(self):
        return self.get_return_url()


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
        response = redirect(settings.LOGOUT_REDIRECT_URL)
        response.delete_cookie(settings.AUTH_PROXY_COOKIE_NAME)
        return response

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
        from datetime import datetime, time

        from django.db import models as django_models
        from django.db.models.functions import Cast

        today = timezone.now().date()
        today_start = timezone.make_aware(datetime.combine(today, time.min))
        today_end = timezone.make_aware(datetime.combine(today, time.max))
        items = (
            Item.objects.for_user(self.request.user)
            .select_related("area")
            .prefetch_related("contexts")
            .prefetch_related("tags")
            .prefetch_related("parent")
            .prefetch_related("documents")
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
                    When(due_date__lt=today_start, then=Value(1000)),
                    # Due today gets very high boost
                    When(
                        Q(due_date__gte=today_start) & Q(due_date__lte=today_end),
                        then=Value(100),
                    ),
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
        from .search import SearchFilter, extract_referenced_ids

        # Keep any project explicitly queried (project:<id>) visible in the
        # suggestions even when it is completed.
        queried_project_ids = extract_referenced_ids(self.get_search_query(), "project")

        search_filter = SearchFilter(
            user=self.request.user,
            areas=areas,
            contexts=contexts,
            projects=Item.objects.projects(
                self.request.user, include_ids=queried_project_ids
            ),
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
                "batch_actions": ItemBatchActions(
                    self.request.user
                ).get_available_actions(),
                "batch_model": ItemBatchActions.model_name(),
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
class ItemTransitionView(HtmxModalActionMixin, FormView):
    """
    Handle item state transitions for logged-in users.
    Supports form-based transitions for decorated methods.
    """

    template_name = "transitions/form.html"

    def get_template_names(self):
        # HTMX requests get the in-place modal partial; plain requests get the
        # full-page form (robust fallback for direct URLs / no-JS).
        if self._is_htmx():
            return ["transitions/_modal.html"]
        return [self.template_name]

    def get_form_class(self):
        return self.transition.form_class

    def get_form_kwargs(self):
        # Transition forms extend TransitionForm and receive the target item
        # so they can build item-aware choices (e.g. valid parents).
        kwargs = super().get_form_kwargs()
        kwargs["item"] = self.item
        return kwargs

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

    def form_valid(self, form):
        """Handle valid form submission - execute transition with form data"""
        self._execute_transition(**form.cleaned_data if form is not None else {})

        if self._is_htmx():
            return self._htmx_refresh_response()

        return super().form_valid(form)

    def form_invalid(self, form):
        """Re-render the form with errors (in the modal for HTMX requests)."""
        if self._is_htmx():
            # 400 so base.js swaps the body back into #modal-container
            # (htmx.config.responseHandling: 4xx -> swap, no error).
            return self.render_to_response(self.get_context_data(form=form), status=400)
        return super().form_invalid(form)

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
            logger.exception(
                "Transition %s failed on item %s", self.transition.name, self.item.pk
            )
            messages.error(self.request, f"Error applying transition: {str(e)}")


@method_decorator(login_required, name="dispatch")
class BatchActionView(HtmxModalActionMixin, FormView):
    """
    Generic executor for @batch_action methods (see batch.py), one URL for
    every registered model/action pair.

    POST-only, two steps — selection payloads (id lists or select_all + q)
    don't belong in a URL:
    - POST without ``confirm``: render the preview (modal for HTMX, full page
      otherwise) with applicable/skipped counts, an unbound form and hidden
      fields echoing the selection.
    - POST with ``confirm=1``: validate the form (if any) and run the action
      on the applicable subset of the re-resolved selection.
    """

    http_method_names = ["post"]
    template_name = "batch/form.html"

    def get_template_names(self):
        if self._is_htmx():
            return ["batch/_modal.html"]
        return [self.template_name]

    def dispatch(self, request, *args, **kwargs):
        actions_class = get_batch_actions_class(kwargs.get("model_name"))
        if actions_class is None:
            raise Http404("Unknown batch model")
        self.actions = actions_class(request.user)
        self.action = self.actions.get_action(kwargs.get("action_slug"))
        if self.action is None:
            raise Http404("Unknown batch action")
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.selection = self.actions.resolve_selection(request.POST)
        self.applicable = self.actions.filter_applicable(self.action, self.selection)
        # Search-based selections may carry M2M joins: count distinct pks.
        self.selected_count = self.selection.order_by().values("pk").distinct().count()
        self.applicable_count = (
            self.applicable.order_by().values("pk").distinct().count()
        )

        if not request.POST.get("confirm"):
            form_class = self.get_form_class()
            form = (
                form_class(user=request.user, selection=self.applicable)
                if form_class
                else None
            )
            return self.render_to_response(self.get_context_data(form=form))

        if not self.get_form_class():
            return self._execute_and_respond()
        return super().post(request, *args, **kwargs)

    def get_form_class(self):
        return self.action.form_class

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        kwargs["selection"] = self.applicable
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "action": self.action,
                "batch_model": self.actions.model_name(),
                "model_verbose_name": self.actions.model._meta.verbose_name,
                "model_verbose_name_plural": self.actions.model._meta.verbose_name_plural,
                "selected_count": self.selected_count,
                "applicable_count": self.applicable_count,
                "skipped_count": self.selected_count - self.applicable_count,
                "impact": self.actions.describe_impact(self.action, self.applicable),
                "selection_fields": self._selection_fields(),
                "return_url": self.get_success_url(),
            }
        )
        return context

    def _selection_fields(self):
        """(name, value) pairs echoing the selection from preview to confirm."""
        fields = []
        for key in ("select_all", "q", "excluded_ids"):
            value = self.request.POST.get(key)
            if value:
                fields.append((key, value))
        for pk in self.request.POST.getlist("ids"):
            fields.append(("ids", pk))
        return fields

    def form_valid(self, form):
        return self._execute_and_respond(**form.cleaned_data)

    def form_invalid(self, form):
        """Re-render the form with errors (in the modal for HTMX requests)."""
        if self._is_htmx():
            # 400 so base.js swaps the body back into #modal-container
            # (htmx.config.responseHandling: 4xx -> swap, no error).
            return self.render_to_response(self.get_context_data(form=form), status=400)
        return super().form_invalid(form)

    def _execute_and_respond(self, **form_data):
        name = self.actions.model._meta.verbose_name
        try:
            applied_count, extra = self.actions.run(
                self.action, self.applicable, **form_data
            )
            message = f"'{self.action.label}' applied to {applied_count} {name}(s)."
            skipped = self.selected_count - self.applicable_count
            if skipped:
                message += f" {skipped} not applicable, skipped."
            if extra:
                message += f" ({extra})"
            messages.success(self.request, message)
        except Exception as e:
            logger.exception(
                "Batch action %s/%s failed",
                self.actions.model_name(),
                self.action.name,
            )
            messages.error(self.request, f"Error applying batch action: {str(e)}")

        if self._is_htmx():
            if self.actions.post_action_refresh == "list":
                return self._htmx_refresh_response()
            # Plain list pages (tags/areas) have no in-place list to refresh:
            # reload. Messages stay queued and render after the reload, so no
            # OOB flash body here (rendering it would consume them).
            response = HttpResponse(status=204)
            response["HX-Refresh"] = "true"
            return response
        return redirect(self.get_success_url())


@method_decorator(login_required, name="dispatch")
class ItemDeleteView(HtmxModalActionMixin, DeleteView):
    """
    Permanently delete an item. A hardcoded action (not an FSM transition),
    available on every item. HTMX requests get a confirmation modal then an
    in-place list refresh (matching the transition modal flow); plain requests
    get a full-page confirmation and a redirect.
    """

    pk_url_kwarg = "item_id"
    context_object_name = "item"

    def get_queryset(self):
        return Item.objects.filter(user=self.request.user)

    def get_template_names(self):
        if self._is_htmx():
            return ["items/_delete_modal.html"]
        return ["items/delete_confirm.html"]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["return_url"] = self.get_return_url()
        return context

    def form_valid(self, form):
        title = self.object.title
        self.object.delete()
        messages.success(self.request, f"Deleted '{title}'.")
        if self._is_htmx():
            return self._htmx_refresh_response()
        return HttpResponseRedirect(self.get_success_url())


@method_decorator(login_required, name="dispatch")
@method_decorator(csrf_exempt, name="dispatch")
class ItemDetailView(UpdateView):
    """
    Item detail/edit. HTMX requests get the in-place modal partial; plain
    requests (deep link, refresh on the pushed /item/<id>/detail/ URL) get a
    full page with the same form.
    """

    model = Item
    pk_url_kwarg = "item_id"
    form_class = ItemForm
    context_object_name = "item"

    def _is_htmx(self):
        return self.request.headers.get("HX-Request") == "true"

    def get_template_names(self):
        if self._is_htmx():
            return ["partials/item_detail_modal.html"]
        return ["items/detail.html"]

    def get_form_kwargs(self):
        return {
            "item_flow": self.object.flow,
            "user": self.request.user,
            **super().get_form_kwargs(),
        }

    def form_valid(self, form):
        self.object = form.save()
        if self._is_htmx():
            # Return the updated modal content after successful save
            return self.render_to_response(self.get_context_data())
        # Plain form post: redirect-after-post to avoid resubmission prompts.
        return HttpResponseRedirect(self.request.path)

    def form_invalid(self, form):
        # 400 so base.js swaps the body back into #modal-container; the plain
        # full-page form re-renders with errors as a normal 200.
        status = 400 if self._is_htmx() else 200
        return self.render_to_response(self.get_context_data(form=form), status=status)

    def get_queryset(self):
        return Item.objects.for_user(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["documents"] = self.object.documents.all()
        return context


@method_decorator(login_required, name="dispatch")
class ItemOffloadView(TemplateView):
    """Standalone mobile quick-capture page (note / photo / voice).

    The page's JS talks to the API with the session cookie + CSRF token;
    the template only has to render {% csrf_token %}.
    """

    template_name = "items/offload.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Single source for the client-side title limit (the API schema
        # mirrors the same model constraint).
        context["MAX_TITLE_LENGTH"] = Item._meta.get_field("title").max_length
        return context


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
        context["documents"] = self.object.documents.all()

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
    endpoint for autocomplete functionality.
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
    endpoint for creating new field values on the fly.
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


# ============================================================================
# AREA CRUD VIEWS
# ============================================================================


@method_decorator(login_required, name="dispatch")
class AreaListView(ListView):
    """Display list of areas for current user"""

    model = Area
    template_name = "areas/area_list.html"
    context_object_name = "areas"
    paginate_by = 20

    def get_queryset(self):
        return (
            Area.objects.filter(user=self.request.user)
            .annotate(task_count=Count("item", filter=Q(item__user=self.request.user)))
            .order_by("name")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "My Areas"
        context["batch_actions"] = AreaBatchActions(
            self.request.user
        ).get_available_actions()
        context["batch_model"] = AreaBatchActions.model_name()
        return context


@method_decorator(login_required, name="dispatch")
class AreaCreateView(ReturnRefererMixin, CreateView):
    """Create a new area"""

    model = Area
    form_class = AreaForm
    template_name = "areas/area_form.html"
    fallback_url = reverse_lazy("area_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request, f"Area '{self.object.name}' created successfully!"
        )
        return response


@method_decorator(login_required, name="dispatch")
class AreaUpdateView(ReturnRefererMixin, UpdateView):
    """Update an existing area"""

    model = Area
    form_class = AreaForm
    template_name = "areas/area_form.html"
    pk_url_kwarg = "area_id"
    fallback_url = reverse_lazy("area_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_queryset(self):
        return Area.objects.filter(user=self.request.user)

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request, f"Area '{self.object.name}' updated successfully!"
        )
        return response


@method_decorator(login_required, name="dispatch")
class AreaDeleteView(ReturnRefererMixin, DeleteView):
    """Delete an area"""

    model = Area
    pk_url_kwarg = "area_id"
    template_name = "areas/area_confirm_delete.html"
    fallback_url = reverse_lazy("area_list")

    def get_queryset(self):
        return Area.objects.filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        area_name = self.get_object().name
        response = super().delete(request, *args, **kwargs)
        messages.success(request, f"Area '{area_name}' deleted successfully!")
        return response


# ============================================================================
# CONTEXT CRUD VIEWS
# ============================================================================


@method_decorator(login_required, name="dispatch")
class ContextListView(ListView):
    """Display list of contexts for current user"""

    model = Context
    template_name = "contexts/context_list.html"
    context_object_name = "contexts"
    paginate_by = 20

    def get_queryset(self):
        return (
            Context.objects.filter(user=self.request.user)
            .annotate(task_count=Count("item", filter=Q(item__user=self.request.user)))
            .order_by("name")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "My Contexts"
        context["batch_actions"] = ContextBatchActions(
            self.request.user
        ).get_available_actions()
        context["batch_model"] = ContextBatchActions.model_name()
        return context


@method_decorator(login_required, name="dispatch")
class ContextCreateView(ReturnRefererMixin, CreateView):
    """Create a new context"""

    model = Context
    form_class = ContextForm
    template_name = "contexts/context_form.html"
    fallback_url = reverse_lazy("context_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request, f"Context '{self.object.name}' created successfully!"
        )
        return response


@method_decorator(login_required, name="dispatch")
class ContextUpdateView(ReturnRefererMixin, UpdateView):
    """Update an existing context"""

    model = Context
    form_class = ContextForm
    template_name = "contexts/context_form.html"
    pk_url_kwarg = "context_id"
    fallback_url = reverse_lazy("context_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_queryset(self):
        return Context.objects.filter(user=self.request.user)

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request, f"Context '{self.object.name}' updated successfully!"
        )
        return response


@method_decorator(login_required, name="dispatch")
class ContextDeleteView(ReturnRefererMixin, DeleteView):
    """Delete a context"""

    model = Context
    pk_url_kwarg = "context_id"
    template_name = "contexts/context_confirm_delete.html"
    fallback_url = reverse_lazy("context_list")

    def get_queryset(self):
        return Context.objects.filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        context_name = self.get_object().name
        response = super().delete(request, *args, **kwargs)
        messages.success(request, f"Context '{context_name}' deleted successfully!")
        return response


# ============================================================================
# TAG CRUD VIEWS
# ============================================================================


@method_decorator(login_required, name="dispatch")
class TagListView(ListView):
    """Display list of tags for current user"""

    model = Tag
    template_name = "tags/tag_list.html"
    context_object_name = "tags"
    paginate_by = 20

    def get_queryset(self):
        return (
            Tag.objects.filter(user=self.request.user)
            .annotate(task_count=Count("item", filter=Q(item__user=self.request.user)))
            .order_by("name")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "My Tags"
        context["batch_actions"] = TagBatchActions(
            self.request.user
        ).get_available_actions()
        context["batch_model"] = TagBatchActions.model_name()
        return context


@method_decorator(login_required, name="dispatch")
class TagCreateView(ReturnRefererMixin, CreateView):
    """Create a new tag"""

    model = Tag
    form_class = TagForm
    template_name = "tags/tag_form.html"
    fallback_url = reverse_lazy("tag_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request, f"Tag '{self.object.name}' created successfully!"
        )
        return response


@method_decorator(login_required, name="dispatch")
class TagUpdateView(ReturnRefererMixin, UpdateView):
    """Update an existing tag"""

    model = Tag
    form_class = TagForm
    template_name = "tags/tag_form.html"
    pk_url_kwarg = "tag_id"
    fallback_url = reverse_lazy("tag_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_queryset(self):
        return Tag.objects.filter(user=self.request.user)

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request, f"Tag '{self.object.name}' updated successfully!"
        )
        return response


@method_decorator(login_required, name="dispatch")
class TagDeleteView(ReturnRefererMixin, DeleteView):
    """Delete a tag"""

    model = Tag
    pk_url_kwarg = "tag_id"
    template_name = "tags/tag_confirm_delete.html"
    fallback_url = reverse_lazy("tag_list")

    def get_queryset(self):
        return Tag.objects.filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        tag_name = self.get_object().name
        response = super().delete(request, *args, **kwargs)
        messages.success(request, f"Tag '{tag_name}' deleted successfully!")
        return response


@method_decorator(login_required, name="dispatch")
class DocumentUploadView(View):
    """
    View for uploading multiple documents to a task.
    """

    def post(self, request, item_id):
        item = get_object_or_404(Item, id=item_id, user=request.user)
        files = request.FILES.getlist("files")

        errors = []
        batch_hashes = set()
        for file in files:
            try:
                attach_document(item, request.user, file, batch_hashes=batch_hashes)
            except DocumentValidationError as error:
                errors.append(f"{file.name}: {error}")

        documents = item.documents.all()
        return render(
            request,
            "partials/document_list.html",
            {"documents": documents, "item_id": item.id, "errors": errors},
        )


@method_decorator(login_required, name="dispatch")
class DocumentDeleteView(View):
    """
    View for deleting a document.
    """

    def post(self, request, document_id):
        document = get_object_or_404(Document, id=document_id, user=request.user)
        item = document.item
        document.delete()

        documents = item.documents.all()
        return render(
            request,
            "partials/document_list.html",
            {"documents": documents, "item_id": item.id},
        )


@method_decorator(login_required, name="dispatch")
class DocumentDownloadView(View):
    """
    Serves a document file to its owner.
    Local storage: streams the file via FileResponse.
    S3 storage: redirects to a pre-signed URL.
    Returns 403 if the requesting user does not own the document.
    """

    def get(self, request, document_id):
        document = get_object_or_404(Document, id=document_id)
        if document.user != request.user:
            raise PermissionDenied

        if settings.STORAGE_BACKEND == "storages.backends.s3boto3.S3Boto3Storage":
            expiry = getattr(settings, "DOCUMENT_PRESIGNED_URL_EXPIRY", 300)
            s3_client = boto3.client(
                "s3",
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                endpoint_url=settings.AWS_S3_ENDPOINT_URL,
                region_name=settings.AWS_S3_REGION_NAME,
            )
            presigned_url = s3_client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
                    "Key": document.file.name,
                },
                ExpiresIn=expiry,
            )
            return HttpResponseRedirect(presigned_url)

        return FileResponse(
            document.file.open("rb"),
            content_type=document.content_type or "application/octet-stream",
            as_attachment=False,
        )


# ============================================================================
# EMAIL INBOX SETTINGS VIEWS
# ============================================================================


@method_decorator(login_required, name="dispatch")
class EmailInboxSettingsView(PermissionRequiredMixin, UpdateView):
    """Configure the user's email-to-task inbox"""

    model = EmailInbox
    form_class = EmailInboxForm
    template_name = "email_inbox/settings.html"
    permission_required = EMAIL_INBOX_PERMISSION
    raise_exception = True
    success_url = reverse_lazy("email_inbox_settings")

    def get_object(self, queryset=None):
        inbox, _ = EmailInbox.objects.get_or_create(user=self.request.user)
        return inbox

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["allowed_senders"] = self.object.allowed_senders.all()
        context.setdefault("sender_form", AllowedSenderForm(inbox=self.object))
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        state = "enabled" if self.object.enabled else "disabled"
        messages.success(self.request, f"Email inbox {state}.")
        return response


@method_decorator(login_required, name="dispatch")
class EmailInboxRegenerateView(PermissionRequiredMixin, View):
    """Regenerate the secret inbox address"""

    permission_required = EMAIL_INBOX_PERMISSION
    raise_exception = True

    def post(self, request):
        inbox, _ = EmailInbox.objects.get_or_create(user=request.user)
        inbox.regenerate_identifier()
        messages.success(request, f"New inbox address generated: {inbox.address}")
        return redirect("email_inbox_settings")


@method_decorator(login_required, name="dispatch")
class AllowedSenderCreateView(PermissionRequiredMixin, CreateView):
    """Whitelist a sender address"""

    model = AllowedSender
    form_class = AllowedSenderForm
    permission_required = EMAIL_INBOX_PERMISSION
    raise_exception = True
    success_url = reverse_lazy("email_inbox_settings")
    # Submitted from the settings page; there is no standalone form template
    http_method_names = ["post"]

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        inbox, _ = EmailInbox.objects.get_or_create(user=self.request.user)
        kwargs["inbox"] = inbox
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Sender '{self.object.email}' whitelisted.")
        return response

    def form_invalid(self, form):
        view = EmailInboxSettingsView()
        view.request = self.request
        view.object = form.inbox
        view.kwargs = {}
        context = view.get_context_data(
            form=EmailInboxForm(user=self.request.user, instance=form.inbox),
            sender_form=form,
        )
        return render(self.request, "email_inbox/settings.html", context)


@method_decorator(login_required, name="dispatch")
class AllowedSenderDeleteView(PermissionRequiredMixin, DeleteView):
    """Remove a whitelisted sender address"""

    model = AllowedSender
    pk_url_kwarg = "sender_id"
    permission_required = EMAIL_INBOX_PERMISSION
    raise_exception = True
    success_url = reverse_lazy("email_inbox_settings")
    # Deleted via the settings page form; there is no confirmation template
    http_method_names = ["post"]

    def get_queryset(self):
        return AllowedSender.objects.filter(inbox__user=self.request.user)

    def form_valid(self, form):
        email = self.object.email
        response = super().form_valid(form)
        messages.success(self.request, f"Sender '{email}' removed.")
        return response
