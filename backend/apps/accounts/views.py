"""Account views.

Balances are computed with aggregate annotations rather than per-object
properties, so listing accounts is a constant number of queries regardless of
how many accounts or transactions exist.
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.money import quantize_money
from apps.core.permissions import IsOwner

from .models import Account, AccountType
from .serializers import AccountPickerSerializer, AccountSerializer, AccountWriteSerializer


def accounts_with_totals(user):
    """Queryset annotated with income, expense and derived balance.

    Uses conditional aggregation: one pass over transactions produces both the
    income and expense sums via `FILTER`-style `Case/When`, instead of two
    separate subqueries.
    """
    money_field = DecimalField(max_digits=18, decimal_places=2)

    # Scope the joined transactions to the account's own owner as well as to
    # the account itself. The FK already guarantees this, but every financial
    # aggregate in this codebase is owner-scoped so one stray row cannot leak
    # between users. Mirrors `Account._own_transactions()`.
    own_transactions = Q(transactions__user=F("user"))

    income_sum = Coalesce(
        Sum(
            "transactions__amount",
            filter=own_transactions & Q(transactions__transaction_type="income"),
        ),
        Value(Decimal("0.00"), output_field=money_field),
        output_field=money_field,
    )
    expense_sum = Coalesce(
        Sum(
            "transactions__amount",
            filter=own_transactions & Q(transactions__transaction_type="expense"),
        ),
        Value(Decimal("0.00"), output_field=money_field),
        output_field=money_field,
    )

    return (
        Account.objects.for_user(user)
        .annotate(
            income_total_annotated=income_sum,
            expense_total_annotated=expense_sum,
            transactions_count=Count("transactions", filter=own_transactions, distinct=True),
        )
        .annotate(
            current_balance_annotated=ExpressionWrapper(
                F("opening_balance")
                + F("income_total_annotated")
                - F("expense_total_annotated"),
                output_field=money_field,
            )
        )
    )


class AccountViewSet(viewsets.ModelViewSet):
    """CRUD for accounts.

    list:     GET    /api/accounts/
    create:   POST   /api/accounts/
    read:     GET    /api/accounts/{id}/
    update:   PATCH  /api/accounts/{id}/
    delete:   DELETE /api/accounts/{id}/
    picker:   GET    /api/accounts/picker/
    summary:  GET    /api/accounts/summary/
    """

    permission_classes = [IsOwner]
    filterset_fields = ["account_type", "is_active"]
    search_fields = ["name", "institution"]
    ordering_fields = ["name", "sort_order", "created_at", "current_balance_annotated"]
    ordering = ["sort_order", "name"]

    def get_queryset(self):
        return accounts_with_totals(self.request.user)

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return AccountWriteSerializer
        if self.action == "picker":
            return AccountPickerSerializer
        return AccountSerializer

    def create(self, request, *args, **kwargs):
        """Create, then respond with the full read representation.

        The write serializer has no balance fields; the client needs the
        computed balance to render the new account row immediately.
        """
        write_serializer = self.get_serializer(data=request.data)
        write_serializer.is_valid(raise_exception=True)
        # Route through perform_create so the `user` assignment stays in one
        # place, rather than being duplicated here and in the base class.
        self.perform_create(write_serializer)
        instance = write_serializer.instance

        # Re-read through the annotated queryset so balance annotations exist.
        fresh = self.get_queryset().get(pk=instance.pk)
        read_serializer = AccountSerializer(fresh, context=self.get_serializer_context())
        headers = self.get_success_headers(read_serializer.data)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        """Update, then respond with the full read representation."""
        partial = kwargs.pop("partial", False)
        instance = self.get_object()

        write_serializer = self.get_serializer(instance, data=request.data, partial=partial)
        write_serializer.is_valid(raise_exception=True)
        write_serializer.save()

        fresh = self.get_queryset().get(pk=instance.pk)
        read_serializer = AccountSerializer(fresh, context=self.get_serializer_context())
        return Response(read_serializer.data)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        """Refuse deletion while transactions reference the account.

        Deleting would orphan financial history; `is_active=False` is offered
        as the reversible alternative.
        """
        account = self.get_object()

        if account.transactions.exists():
            count = account.transactions.count()
            return Response(
                {
                    "detail": (
                        f"این حساب {count} تراکنش دارد. برای پنهان کردن آن، حساب را "
                        "غیرفعال کنید؛ در غیر این صورت ابتدا تراکنش‌ها را جابه‌جا کنید."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=["get"])
    def picker(self, request):
        queryset = (
            accounts_with_totals(request.user)
            .filter(is_active=True)
            .order_by("sort_order", "name")
        )
        serializer = AccountPickerSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Totals across accounts, used on the dashboard and assets screens."""
        queryset = self.get_queryset().filter(is_active=True)

        total = Decimal("0.00")
        included = Decimal("0.00")
        by_type: dict[str, Decimal] = {}

        for account in queryset:
            balance = quantize_money(account.current_balance_annotated)
            total += balance
            if account.include_in_total:
                included += balance
            label = account.get_account_type_display()
            by_type[label] = by_type.get(label, Decimal("0.00")) + balance

        return Response(
            {
                "total_balance": str(quantize_money(total)),
                "included_balance": str(quantize_money(included)),
                "accounts_count": queryset.count(),
                "by_type": [
                    {"label": label, "total": str(quantize_money(value))}
                    for label, value in sorted(by_type.items(), key=lambda kv: -kv[1])
                ],
                "types": [{"value": v, "label": l} for v, l in AccountType.choices],
            }
        )
