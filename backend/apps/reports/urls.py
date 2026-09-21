from django.urls import path

from .views import (
    BudgetVsActualView,
    DashboardView,
    MonthlyTrendView,
    ReportsView,
    SpendingByCategoryView,
)

urlpatterns = [
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("reports/", ReportsView.as_view(), name="reports"),
    path("reports/spending-by-category/", SpendingByCategoryView.as_view(), name="report-spending"),
    path("reports/monthly-trend/", MonthlyTrendView.as_view(), name="report-trend"),
    path("reports/budget-vs-actual/", BudgetVsActualView.as_view(), name="report-budget"),
]
