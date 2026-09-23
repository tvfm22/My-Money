"""SMS import views.

Endpoints
---------
    POST   /api/sms/parse/                       read messages, save nothing
    GET    /api/sms/batches/                     import history
    POST   /api/sms/batches/                     read and stage a batch
    GET    /api/sms/batches/{id}/                one batch with its items
    PATCH  /api/sms/batches/{id}/                rename / re-point at an account
    DELETE /api/sms/batches/{id}/                discard a batch
    POST   /api/sms/batches/{id}/commit/         write transactions
    GET    /api/sms/batches/{id}/reconcile/      what the SMS balances imply
    POST   /api/sms/batches/{id}/reconcile/apply/  set the opening balance
    PATCH  /api/sms/items/{id}/                  classify one item
    POST   /api/sms/items/bulk/                  classify a selection
    GET    /api/sms/reminder/                    the monthly prompt's state
    POST   /api/sms/reminder/                    dismiss it for a month
    GET    /api/sms/auto-import/                 the switch, and when it last ran
    PATCH  /api/sms/auto-import/                 turn automatic reading on/off
    POST   /api/sms/auto-import/sync/            check for messages not yet staged

Why the parse endpoint saves nothing
------------------------------------
Reading and staging are separate calls so the client can show a preview before
committing anything to the database. `POST /batches/` is the one that stores, and
it stores into the staging tables only — the ledger is written by `/commit/`.
"""

from __future__ import annotations

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.jalali import month_label
from apps.core.permissions import IsOwner
from apps.transactions.models import Transaction
from apps.transactions.serializers import TransactionSerializer

from .models import SmsImportBatch, SmsImportItem
from .serializers import (
    SmsAutoImportToggleSerializer,
    SmsBulkUpdateRequestSerializer,
    SmsCommitRequestSerializer,
    SmsImportBatchSerializer,
    SmsImportBatchSummarySerializer,
    SmsImportItemSerializer,
    SmsParseRequestSerializer,
    SmsReminderDismissSerializer,
    SmsSyncRequestSerializer,
)

from .services import (
    auto_import_state,
    bulk_update_items,
    commit_batch,
    create_batch,
    dismiss_reminder,
    parse_messages,
    previous_period,
    reminder_state,
    set_auto_import,
    sync_messages,
)
from .services import apply_balance_reconciliation, balance_reconciliation


class SmsParsePreviewView(APIView):
    """Read messages and report what was found, writing nothing.

    The response is exactly what the preview panel renders: one entry per
    message with every parsed field, its warnings, and a per-field confidence.
    Because nothing is stored, the client can call this on every paste without
    leaving rows behind.
    """

    permission_classes = [IsOwner]

    def post(self, request):
        serializer = SmsParseRequestSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        messages = data.get("messages")
        pairs = (
            [(item.get("sender", ""), item["body"]) for item in messages]
            if messages
            else None
        )

        parsed = parse_messages(raw_text=data.get("text", ""), messages=pairs)

        year, month = data.get("period_year"), data.get("period_month")
        if year is None:
            year, month = previous_period()

        readable = [item for item in parsed if item.is_usable]
        return Response(
            {
                "period": {"year": year, "month": month, "label": month_label(year, month)},
                "summary": {
                    "total": len(parsed),
                    "readable": len(readable),
                    "without_balance": sum(1 for item in parsed if item.balance_after is None),
                    "not_transaction": sum(1 for item in parsed if not item.is_transaction),
                    "low_confidence": sum(1 for item in readable if item.low_confidence),
                },
                "messages": [item.to_dict() for item in parsed],
            }
        )


class SmsImportBatchViewSet(viewsets.ModelViewSet):
    """Batches of staged messages, and the actions that act on them."""

    permission_classes = [IsOwner]
    ordering = ["-created_at", "-id"]

    def get_queryset(self):
        return SmsImportBatch.objects.for_user(self.request.user).with_items()

    def get_serializer_class(self):
        if self.action in ("retrieve", "create"):
            return SmsImportBatchSerializer
        return SmsImportBatchSummarySerializer

    def create(self, request, *args, **kwargs):
        """Stage a batch: parse the pasted text and store rows for review."""
        serializer = SmsParseRequestSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        messages = data.get("messages")
        pairs = (
            [(item.get("sender", ""), item["body"]) for item in messages]
            if messages
            else None
        )

        batch = create_batch(
            request.user,
            raw_text=data.get("text", ""),
            messages=pairs,
            period_year=data.get("period_year"),
            period_month=data.get("period_month"),
            source_label=data.get("source_label", ""),
            account=data.get("account"),
        )

        read_serializer = SmsImportBatchSerializer(
            batch, context=self.get_serializer_context()
        )
        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def commit(self, request, pk=None):
        """Write the confirmed rows into the ledger."""
        batch = self.get_object()

        serializer = SmsCommitRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = commit_batch(
            request.user, batch, item_ids=serializer.validated_data.get("item_ids")
        )

        batch.refresh_from_db()
        created = result["transactions"]
        return Response(
            {
                "batch": SmsImportBatchSerializer(
                    batch, context=self.get_serializer_context()
                ).data,
                "imported_count": result["imported_count"],
                "missing_category_count": result["missing_category_count"],
                "incomplete_count": result["incomplete_count"],
                "not_transaction_count": result["not_transaction_count"],
                "transactions": TransactionSerializer(
                    Transaction.objects.with_relations().filter(
                        pk__in=[tx.pk for tx in created]
                    ),
                    many=True,
                    context=self.get_serializer_context(),
                ).data,
                "message": self._commit_message(result),
            }
        )

    @staticmethod
    def _commit_message(result: dict) -> str:
        """A sentence that says what happened *and* what did not."""
        imported = result["imported_count"]
        parts = [f"{imported} تراکنش ثبت شد."] if imported else ["چیزی ثبت نشد."]
        if result["missing_category_count"]:
            parts.append(
                f"{result['missing_category_count']} قلم بدون دسته‌بندی ماند؛ برای ثبت، دسته‌بندی انتخاب کنید."
            )
        if result["incomplete_count"]:
            parts.append(
                f"{result['incomplete_count']} قلم مبلغ یا جهت خوانا نداشت و ثبت نشد."
            )
        if result["not_transaction_count"]:
            parts.append(
                f"{result['not_transaction_count']} پیام غیرتراکنشی نادیده گرفته شد."
            )
        return " ".join(parts)

    @action(detail=True, methods=["get"])
    def reconcile(self, request, pk=None):
        """What the balances printed in this batch imply about the account."""
        return Response(balance_reconciliation(request.user, self.get_object()))

    @action(detail=True, methods=["post"], url_path="reconcile/apply")
    def reconcile_apply(self, request, pk=None):
        """Set the account's opening balance from the newest SMS reading."""
        result = apply_balance_reconciliation(request.user, self.get_object())
        if not result.get("available"):
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)


class SmsImportItemViewSet(mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Classify staged items, one at a time or by selection.

    Only update is exposed: items are created by `POST /api/sms/batches/` and
    deleted with their batch, so a client can never invent or orphan a staged
    row.
    """

    permission_classes = [IsOwner]
    serializer_class = SmsImportItemSerializer

    def get_queryset(self):
        return SmsImportItem.objects.for_user(self.request.user).with_relations()

    def update(self, request, *args, **kwargs):
        """PATCH, answering with the full review representation."""
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return Response(self.get_serializer(instance).data)

    @action(detail=False, methods=["post"])
    def bulk(self, request):
        """Apply one category/account/status to a whole selection."""
        serializer = SmsBulkUpdateRequestSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        items = self.get_queryset().filter(id__in=data["item_ids"])
        fields = {
            key: value
            for key, value in data.items()
            if key in ("category", "account", "spending_type", "status")
        }

        result = bulk_update_items(request.user, items, **fields)
        return Response(
            {
                **result,
                "items": self.get_serializer(
                    self.get_queryset().filter(id__in=data["item_ids"]), many=True
                ).data,
            }
        )


class SmsReminderView(APIView):
    """The monthly prompt: read its state, or dismiss it for a month."""

    permission_classes = [IsOwner]

    def get(self, request):
        return Response(reminder_state(request.user))

    def post(self, request):
        serializer = SmsReminderDismissSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dismiss_reminder(
            request.user,
            serializer.validated_data["period_year"],
            serializer.validated_data["period_month"],
        )
        return Response(reminder_state(request.user))


class SmsAutoImportView(APIView):
    """The automatic-reading switch, and the state around it.

    Read and write are one endpoint because the client only ever wants the
    resulting state: the toggle is rendered from the response, so it can never
    show a value the server did not accept.
    """

    permission_classes = [IsOwner]

    def get(self, request):
        return Response(auto_import_state(request.user))

    def patch(self, request):
        serializer = SmsAutoImportToggleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        set_auto_import(request.user, enabled=serializer.validated_data["enabled"])
        return Response(auto_import_state(request.user))


class SmsSyncView(APIView):
    """Look for messages that have not been staged yet.

    This is the fallback behind the automatic pass: whether the app looks on its
    own or the user presses «خواندن پیامک‌های قبلی», the same call runs, so the
    two paths cannot disagree about what counts as new.

    Text is optional. Without it the call records that a check happened and
    reports the backlog — which is exactly what opening the screen should do
    when nothing new has been pasted.
    """

    permission_classes = [IsOwner]

    def post(self, request):
        serializer = SmsSyncRequestSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        messages = data.get("messages")
        pairs = (
            [(item.get("sender", ""), item["body"]) for item in messages]
            if messages
            else None
        )

        return Response(
            sync_messages(
                request.user,
                raw_text=data.get("text", ""),
                messages=pairs,
                period_year=data.get("period_year"),
                period_month=data.get("period_month"),
                source_label=data.get("source_label", ""),
                account=data.get("account"),
            )
        )



