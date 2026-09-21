"""Transaction and tag views."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db import transaction as db_transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.jalali import (
    PERSIAN_MONTHS,
    jalali_month_bounds,
    month_progress,
    resolve_month_param,
)
from apps.core.money import quantize_money
from apps.core.permissions import IsOwner

from .filters import TransactionFilter
from .models import Tag, Transaction, TransactionType
from .serializers import (
    TagSerializer,
    TransactionBulkCreateSerializer,
    TransactionSerializer,
    TransactionWriteSerializer,
)


class TransactionViewSet(viewsets.ModelViewSet):
    """CRUD plus aggregation helpers for transactions.

    list:      GET    /api/transactions/
    create:    POST   /api/transactions/
    read:      GET    /api/transactions/{id}/
    update:    PATCH  /api/transactions/{id}/
    delete:    DELETE /api/transactions/{id}/
    recent:    GET    /api/transactions/recent/
    summary:   GET    /api/transactions/summary/
    bulk:      POST   /api/transactions/bulk/
    """

    permission_classes = [IsOwner]
    filterset_class = TransactionFilter
    search_fields = ["description", "note", "category__name", "account__name"]
    ordering_fields = ["occurred_on", "amount", "created_at"]
    ordering = ["-occurred_on", "-created_at", "-id"]

    def get_queryset(self):
        return (
            Transaction.objects.for_user(self.request.user)
            .with_relations()
            .order_by(*self.ordering)
        )

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return TransactionWriteSerializer
        if self.action == "bulk":
            return TransactionBulkCreateSerializer
        return TransactionSerializer

    def create(self, request, *args, **kwargs):
        """Create, then respond with the full read representation.

        The write serializer only knows the input fields. The client needs the
        derived display strings (formatted amount, Jalali date, category
        detail) to render the new row without a follow-up request, so the
        response is re-serialized with the read serializer.
        """
        write_serializer = self.get_serializer(data=request.data)
        write_serializer.is_valid(raise_exception=True)
        instance = write_serializer.save()

        read_serializer = TransactionSerializer(instance, context=self.get_serializer_context())
        headers = self.get_success_headers(read_serializer.data)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        """Update, then respond with the full read representation."""
        partial = kwargs.pop("partial", False)
        instance = self.get_object()

        write_serializer = self.get_serializer(instance, data=request.data, partial=partial)
        write_serializer.is_valid(raise_exception=True)
        instance = write_serializer.save()

        read_serializer = TransactionSerializer(instance, context=self.get_serializer_context())
        return Response(read_serializer.data)

    # ------------------------------------------------------------------
    # Convenience endpoints
    # ------------------------------------------------------------------

    @action(detail=False, methods=["get"])
    def recent(self, request):
        """The N most recent transactions for the dashboard.

        Capped hard: this feeds a compact home-screen list, and returning more
        than a screenful would be wasted bandwidth on a phone.
        """
        try:
            limit = min(int(request.query_params.get("limit", 8)), 50)
        except (TypeError, ValueError):
            limit = 8

        queryset = self.get_queryset()[:limit]
        serializer = TransactionSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Income/expense totals and counts for the current filter set.

        Respects every active filter, so the numbers always describe exactly
        the rows the user is looking at.
        """
        queryset = self.filter_queryset(self.get_queryset())

        money_field = DecimalField(max_digits=18, decimal_places=2)
        totals = queryset.aggregate(
            income=Coalesce(
                Sum("amount", filter=Q(transaction_type=TransactionType.INCOME)),
                Value(Decimal("0.00"), output_field=money_field),
                output_field=money_field,
            ),
            expense=Coalesce(
                Sum("amount", filter=Q(transaction_type=TransactionType.EXPENSE)),
                Value(Decimal("0.00"), output_field=money_field),
                output_field=money_field,
            ),
            count=Count("id"),
        )

        income = quantize_money(totals["income"])
        expense = quantize_money(totals["expense"])

        return Response(
            {
                "income_total": str(income),
                "expense_total": str(expense),
                "net": str(quantize_money(income - expense)),
                "count": totals["count"],
            }
        )

    @action(detail=False, methods=["post"])
    @db_transaction.atomic
    def bulk(self, request):
        """Create several transactions in one request."""
        serializer = TransactionBulkCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        created_ids = []
        for item in serializer.validated_data["transactions"]:
            item_serializer = TransactionWriteSerializer(context={"request": request})
            instance = item_serializer.create(item)
            created_ids.append(instance.pk)

        # Re-read through the annotated queryset, with tags prefetched, so the
        # response carries the derived display fields the client needs.
        created = list(
            Transaction.objects.with_relations()
            .filter(pk__in=created_ids)
            .order_by("-occurred_on", "-id")
        )

        return Response(
            TransactionSerializer(created, many=True).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["get"])
    def calendar(self, request):
        """Daily income/expense totals for a Jalali month.

        Powers a compact calendar heat view: which days were expensive, which
        were quiet. Returns every day of the month, including empty ones, so
        the client can render a complete grid without filling gaps itself.
        """
        year, month = resolve_month_param(request)

        first, last = jalali_month_bounds(year, month)
        progress = month_progress(year, month)

        rows = (
            Transaction.objects.for_user(request.user)
            .between(first, last)
            .values("occurred_on", "transaction_type")
            .annotate(total=Sum("amount"))
        )

        per_day: dict[dt.date, dict[str, Decimal]] = {}
        for row in rows:
            bucket = per_day.setdefault(
                row["occurred_on"], {"income": Decimal("0.00"), "expense": Decimal("0.00")}
            )
            bucket[row["transaction_type"]] = quantize_money(row["total"])

        days = []
        cursor = first
        while cursor <= last:
            bucket = per_day.get(cursor, {"income": Decimal("0.00"), "expense": Decimal("0.00")})
            income = quantize_money(bucket["income"])
            expense = quantize_money(bucket["expense"])
            days.append(
                {
                    "date": cursor.isoformat(),
                    "income": str(income),
                    "expense": str(expense),
                    "net": str(quantize_money(income - expense)),
                    # Lets the client size a heat cell without a second pass.
                    "has_activity": income > 0 or expense > 0,
                }
            )
            cursor += dt.timedelta(days=1)

        return Response(
            {
                "year": year,
                "month": month,
                "month_name": PERSIAN_MONTHS[month - 1],
                "days_in_month": progress["days_in_month"],
                "days_elapsed": progress["days_elapsed"],
                "days": days,
            }
        )


class TagViewSet(viewsets.ModelViewSet):
    """CRUD for tags.

    list:   GET    /api/tags/
    create: POST   /api/tags/
    delete: DELETE /api/tags/{id}/
    """

    serializer_class = TagSerializer
    permission_classes = [IsOwner]
    search_fields = ["name"]
    ordering = ["name"]
    pagination_class = None  # tag lists are small; paging them adds no value

    def get_queryset(self):
        # Annotate usage counts so the UI can show "used 12 times" and warn
        # before deleting a tag that is in use.
        return Tag.objects.for_user(self.request.user).annotate(
            usage_count=Count("transactions")
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
