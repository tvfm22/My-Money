"""Debt views."""

from __future__ import annotations

import datetime as dt

from django.db import transaction as db_transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import IsOwner

from .models import Debt, DebtDirection, DebtPayment
from .serializers import (
    DebtPaymentSerializer,
    DebtPaymentWriteSerializer,
    DebtSerializer,
    DebtWriteSerializer,
    _sync_settled_state,
    debt_totals,
)


class DebtViewSet(viewsets.ModelViewSet):
    """CRUD for debts and receivables, plus payments and summaries.

    list:        GET    /api/debts/
    create:      POST   /api/debts/
    read:        GET    /api/debts/{id}/
    update:      PATCH  /api/debts/{id}/
    delete:      DELETE /api/debts/{id}/
    summary:     GET    /api/debts/summary/
    upcoming:    GET    /api/debts/upcoming/
    pay:         POST   /api/debts/{id}/payments/
    payments:    GET    /api/debts/{id}/payments/
    """

    permission_classes = [IsOwner]
    filterset_fields = ["direction"]
    search_fields = ["counterparty", "description", "note"]
    ordering_fields = ["created_at", "due_on", "principal"]
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = Debt.objects.for_user(self.request.user).with_payments()

        # `status` is derived, so it cannot be a plain filter field. Doing it
        # here keeps the API surface consistent with the other modules.
        status_param = self.request.query_params.get("status")
        if status_param:
            today = dt.date.today()
            if status_param == "settled":
                queryset = queryset.filter(settled_at__isnull=False)
            elif status_param == "overdue":
                queryset = queryset.filter(
                    settled_at__isnull=True, due_on__lt=today, due_on__isnull=False
                )
            elif status_param == "open":
                queryset = queryset.filter(settled_at__isnull=True)
            elif status_param == "active":
                queryset = queryset.filter(settled_at__isnull=True, due_on__gte=today)

        return queryset

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return DebtWriteSerializer
        return DebtSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        debt = serializer.save(user=request.user)
        return Response(
            DebtSerializer(debt).data, status=status.HTTP_201_CREATED
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        debt = serializer.save()
        return Response(DebtSerializer(debt).data)

    # ------------------------------------------------------------------
    # Summary and upcoming
    # ------------------------------------------------------------------

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Totals for both directions, plus overdue and upcoming figures."""
        payload = debt_totals(request.user)

        # Upcoming = not settled, has a due date, due within 30 days or overdue.
        today = dt.date.today()
        horizon = today + dt.timedelta(days=30)

        upcoming = (
            Debt.objects.for_user(request.user)
            .with_payments()
            .filter(settled_at__isnull=True, due_on__isnull=False, due_on__lte=horizon)
            .order_by("due_on")[:10]
        )

        payload["upcoming"] = DebtSerializer(upcoming, many=True).data
        return Response(payload)

    @action(detail=False, methods=["get"])
    def upcoming(self, request):
        """Debts due soon or already overdue, soonest first."""
        try:
            days = min(int(request.query_params.get("days", 30)), 365)
        except (TypeError, ValueError):
            days = 30

        today = dt.date.today()
        horizon = today + dt.timedelta(days=days)

        queryset = (
            Debt.objects.for_user(request.user)
            .with_payments()
            .filter(settled_at__isnull=True, due_on__isnull=False, due_on__lte=horizon)
            .order_by("due_on")
        )

        return Response(
            {
                "overdue": DebtSerializer(
                    [d for d in queryset if d.is_overdue], many=True
                ).data,
                "due_soon": DebtSerializer(
                    [d for d in queryset if not d.is_overdue], many=True
                ).data,
                "horizon_days": days,
            }
        )

    # ------------------------------------------------------------------
    # Payments
    # ------------------------------------------------------------------

    @action(detail=True, methods=["get", "post"], url_path="payments")
    def payments(self, request, pk=None):
        """List payments for a debt, or record a new one.

        A partial payment is the normal case, so this is a first-class endpoint
        rather than something the client approximates by editing the debt.
        """
        debt = self.get_object()

        if request.method == "GET":
            return Response(DebtPaymentSerializer(debt.payments.all(), many=True).data)

        serializer = DebtPaymentWriteSerializer(
            data=request.data, context={"request": request, "debt": debt}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        # Re-read so the response carries post-payment derived figures.
        debt.refresh_from_db()
        return Response(
            {
                "debt": DebtSerializer(debt).data,
                "totals": debt_totals(request.user),
            },
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=["delete"],
        url_path=r"payments/(?P<payment_id>[^/.]+)",
    )
    def delete_payment(self, request, pk=None, payment_id=None):
        """Remove a payment, reverting the debt's settled state if needed."""
        debt = self.get_object()

        try:
            payment = debt.payments.get(pk=payment_id)
        except DebtPayment.DoesNotExist:
            return Response(
                {"detail": "این پرداخت پیدا نشد."}, status=status.HTTP_404_NOT_FOUND
            )

        with db_transaction.atomic():
            payment.delete()
            _sync_settled_state(debt)

        debt.refresh_from_db()
        return Response({"debt": DebtSerializer(debt).data, "totals": debt_totals(request.user)})
