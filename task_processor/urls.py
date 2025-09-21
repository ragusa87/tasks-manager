"""
URL configuration for document_processing project.

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
    DashboardActivityView,
    DashboardChartsView,
    DashboardSearchView,
    DashboardStatsView,
    DashboardUrgentView,
    DashboardView,
    InboxView,
    ItemCreateView,
    ItemTransitionView,
    ItemUpdateView,
    LoginView,
    LogoutView,
)

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("", DashboardView.as_view(), name="dashboard"),
    path("inbox/", InboxView.as_view(), name="inbox"),
    path("item/create/", ItemCreateView.as_view(), name="item_create"),
    path("item/<int:item_id>/update/", ItemUpdateView.as_view(), name="item_update"),
    path("item/<int:item_id>/transition/<str:transition_slug>/", ItemTransitionView.as_view(), name="item_transition"),
    path("dashboard/stats/", DashboardStatsView.as_view(), name="dashboard_stats"),
    path("dashboard/charts/", DashboardChartsView.as_view(), name="dashboard_charts"),
    path("dashboard/urgent/", DashboardUrgentView.as_view(), name="dashboard_urgent"),
    path("dashboard/activity/", DashboardActivityView.as_view(), name="dashboard_activity"),
    path("dashboard/search/", DashboardSearchView.as_view(), name="dashboard_search"),
]
