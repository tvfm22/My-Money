"""SMS routes. Mounted under ``/api/`` by `config.urls`."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    SmsImportBatchViewSet,
    SmsImportItemViewSet,
    SmsParsePreviewView,
    SmsReminderView,
)

router = DefaultRouter()
router.register("sms/batches", SmsImportBatchViewSet, basename="sms-batch")
router.register("sms/items", SmsImportItemViewSet, basename="sms-item")

urlpatterns = router.urls + [
    # Reading and staging are different calls on purpose: `/parse/` writes
    # nothing, so the client can preview before storing anything.
    path("sms/parse/", SmsParsePreviewView.as_view(), name="sms-parse"),
    path("sms/reminder/", SmsReminderView.as_view(), name="sms-reminder"),
]
