"""
URL configuration for task_processing project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.urls import path

from .views import (
    AreaCreateView,
    AreaDeleteView,
    AreaListView,
    AreaUpdateView,
    AutocompleteView,
    ContextCreateView,
    ContextDeleteView,
    ContextListView,
    ContextUpdateView,
    CreateFieldView,
    DashboardStatsView,
    DashboardView,
    ItemCreateView,
    ItemDetailView,
    ItemTransitionView,
    ItemUpdateView,
    LoginView,
    LogoutView,
    TagCreateView,
    TagDeleteView,
    TagListView,
    TagUpdateView,
)

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("", DashboardView.as_view(), name="dashboard"),
    path("item/create/", ItemCreateView.as_view(), name="item_create"),
    path("item/<int:item_id>/detail/", ItemDetailView.as_view(), name="item_detail"),
    path("item/<int:item_id>/update/", ItemUpdateView.as_view(), name="item_update"),
    path(
        "item/<int:item_id>/transition/<str:transition_slug>/",
        ItemTransitionView.as_view(),
        name="item_transition",
    ),
    path("dashboard/stats/", DashboardStatsView.as_view(), name="dashboard_stats"),
    path(
        "autocomplete/search/<str:field_type>/",
        AutocompleteView.as_view(),
        name="autocomplete",
    ),
    path(
        "autocomplete/create/<str:field_type>/",
        CreateFieldView.as_view(),
        name="create_field",
    ),
    # Areas
    path("areas/", AreaListView.as_view(), name="area_list"),
    path("areas/create/", AreaCreateView.as_view(), name="area_create"),
    path("areas/<int:area_id>/update/", AreaUpdateView.as_view(), name="area_update"),
    path("areas/<int:area_id>/delete/", AreaDeleteView.as_view(), name="area_delete"),
    # Contexts
    path("contexts/", ContextListView.as_view(), name="context_list"),
    path("contexts/create/", ContextCreateView.as_view(), name="context_create"),
    path(
        "contexts/<int:context_id>/update/",
        ContextUpdateView.as_view(),
        name="context_update",
    ),
    path(
        "contexts/<int:context_id>/delete/",
        ContextDeleteView.as_view(),
        name="context_delete",
    ),
    # Tags
    path("tags/", TagListView.as_view(), name="tag_list"),
    path("tags/create/", TagCreateView.as_view(), name="tag_create"),
    path("tags/<int:tag_id>/update/", TagUpdateView.as_view(), name="tag_update"),
    path("tags/<int:tag_id>/delete/", TagDeleteView.as_view(), name="tag_delete"),
]
