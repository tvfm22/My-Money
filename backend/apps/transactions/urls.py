from rest_framework.routers import DefaultRouter

from .views import TagViewSet, TransactionViewSet

router = DefaultRouter()
router.register("transactions", TransactionViewSet, basename="transaction")
router.register("tags", TagViewSet, basename="tag")

urlpatterns = router.urls
