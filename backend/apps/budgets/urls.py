from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import BudgetItemViewSet, BudgetOverviewView, BudgetViewSet

router = DefaultRouter()
router.register("budgets", BudgetViewSet, basename="budget")
router.register("budget-items", BudgetItemViewSet, basename="budget-item")

urlpatterns = [
    # Declared before the router so the static path is not captured by
    # /budgets/{pk}/.
    path("budgets-overview/", BudgetOverviewView.as_view(), name="budgets-overview"),
    *router.urls,
]
