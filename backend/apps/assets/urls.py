from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import AssetGrowthView, AssetViewSet, NetWorthHistoryView, NetWorthView

router = DefaultRouter()
router.register("assets", AssetViewSet, basename="asset")

urlpatterns = [
    # Static paths before the router so they are not read as /assets/{pk}/.
    path("net-worth/", NetWorthView.as_view(), name="net-worth"),
    path("net-worth/history/", NetWorthHistoryView.as_view(), name="net-worth-history"),
    path("assets/growth/", AssetGrowthView.as_view(), name="asset-growth"),
    *router.urls,
]
