"""Debt serializers and aggregate helpers."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db import transaction as db_transaction
from django.utils import timezone
from rest_framework import serializers

from apps.core.jalali import format_jalali, format_money, format_percent
from apps.core.money import quantize_money, to_decimal

from .models import Debt, DebtDirection, DebtPayment, DebtStatus


class DebtPaymentSerializer(serializers.ModelSerializer):
    """Read serializer for a payment."""

    paid_on_display = serializers.SerializerMethodField()
    amount_display = serializers.SerializerMethodField()

    class Meta:
        model = DebtPayment
        fields = (
            "id",
            "amount",
            "amount_display",
            "paid_on",
            "paid_on_display",
            "note",
            "account",
            "created_at",
        )
        read_only_fields = ("id", "created_at")

    def get_paid_on_display(self, obj) -> str:
        return format_jalali(obj.paid_on, style="short")

    def get_amount_display(self, obj) -> str:
        return format_money(obj.amount)


class DebtSerializer(serializers.ModelSerializer):
    """Read serializer, carrying all derived figures the UI needs."""

    principal = serializers.SerializerMethodField()
    paid_amount = serializers.SerializerMethodField()
    remaining_amount = serializers.SerializerMethodField()

    principal_display = serializers.SerializerMethodField()
    paid_display = serializers.SerializerMethodField()
    remaining_display = serializers.SerializerMethodField()
    paid_percent = serializers.SerializerMethodField()
    paid_percent_display = serializers.SerializerMethodField()

    status = serializers.CharField(read_only=True)
    status_label = serializers.CharField(read_only=True)
    direction_label = serializers.CharField(read_only=True)

    issued_on_display = serializers.SerializerMethodField()
    due_on_display = serializers.SerializerMethodField()
    due_relative = serializers.SerializerMethodField()

    is_overdue = serializers.BooleanField(read_only=True)
    is_settled = serializers.BooleanField(read_only=True)
    days_until_due = serializers.IntegerField(read_only=True, allow_null=True)

    payments = DebtPaymentSerializer(many=True, read_only=True)
    payments_count = serializers.SerializerMethodField()
    account_name = serializers.CharField(source="account.name", read_only=True, default=None)

    class Meta:
        model = Debt
        fields = (
            "id",
            "direction",
            "direction_label",
            "counterparty",
            "principal",
            "principal_display",
            "paid_amount",
            "paid_display",
            "remaining_amount",
            "remaining_display",
            "paid_percent",
            "paid_percent_display",
            "status",
            "status_label",
            "issued_on",
            "issued_on_display",
            "due_on",
            "due_on_display",
            "due_relative",
            "is_overdue",
            "is_settled",
            "days_until_due",
            "description",
            "note",
            "account",
            "account_name",
            "payments",
            "payments_count",
            "settled_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "settled_at", "created_at", "updated_at")

    def get_principal(self, obj) -> str:
        return str(quantize_money(obj.principal))

    def get_paid_amount(self, obj) -> str:
        return str(quantize_money(obj.paid_amount))

    def get_remaining_amount(self, obj) -> str:
        return str(quantize_money(obj.remaining_amount))

    def get_principal_display(self, obj) -> str:
        return format_money(obj.principal)

    def get_paid_display(self, obj) -> str:
        return format_money(obj.paid_amount)

    def get_remaining_display(self, obj) -> str:
        return format_money(obj.remaining_amount)

    def get_paid_percent(self, obj) -> str:
        return str(obj.paid_percent)

    def get_paid_percent_display(self, obj) -> str:
        return format_percent(obj.paid_percent)

    def get_issued_on_display(self, obj) -> str | None:
        return format_jalali(obj.issued_on, style="short") if obj.issued_on else None

    def get_due_on_display(self, obj) -> str | None:
        return format_jalali(obj.due_on, style="short") if obj.due_on else None

    def get_due_relative(self, obj) -> str | None:
        """Human phrasing of the due date, e.g. '۲ روز مانده' / '۳ روز گذشته'."""
        days = obj.days_until_due
        if days is None:
            return None
        if obj.is_settled:
            return "تسویه شده"

        from apps.core.jalali import to_persian_digits

        if days == 0:
            return "سررسید امروز"
        if days == 1:
            return "فردا سررسید"
        if days > 1:
            return to_persian_digits(f"{days} روز مانده")
        return to_persian_digits(f"{abs(days)} روز گذشته")

    def get_payments_count(self, obj) -> int:
        return obj.payments.count()


class DebtWriteSerializer(serializers.ModelSerializer):
    """Create/update a debt."""

    class Meta:
        model = Debt
        fields = (
            "id",
            "direction",
            "counterparty",
            "principal",
            "issued_on",
            "due_on",
            "description",
            "note",
            "account",
        )
        read_only_fields = ("id",)

    def validate_principal(self, value):
        amount = quantize_money(to_decimal(value))
        if amount <= 0:
            raise serializers.ValidationError("مبلغ باید بیشتر از صفر باشد.")
        if amount > Decimal("999999999999999.99"):
            raise serializers.ValidationError("مبلغ وارد شده بیش از حد بزرگ است.")
        return amount

    def validate_counterparty(self, value):
        cleaned = (value or "").strip()
        if not cleaned:
            raise serializers.ValidationError("نام طرف حساب را وارد کنید.")
        return cleaned

    def validate_account(self, value):
        if value is None:
            return value
        request = self.context.get("request")
        if request and value.user_id != request.user.id:
            raise serializers.ValidationError("حساب انتخاب‌شده معتبر نیست.")
        return value

    def validate_due_on(self, value):
        if value is None:
            return value
        # A due date far in the past is almost always a typo.
        if value < dt.date(1300 + 621, 1, 1):
            raise serializers.ValidationError("تاریخ سررسید معتبر نیست.")
        return value

    def validate(self, attrs):
        instance = self.instance

        principal = attrs.get("principal", getattr(instance, "principal", None))
        issued_on = attrs.get("issued_on", getattr(instance, "issued_on", None))
        due_on = attrs.get("due_on", getattr(instance, "due_on", None))

        if issued_on and due_on and due_on < issued_on:
            raise serializers.ValidationError(
                {"due_on": "تاریخ سررسید نمی‌تواند قبل از تاریخ ایجاد باشد."}
            )

        # On update, the principal cannot drop below what has already been paid,
        # which would make the remaining balance negative and the status lie.
        if instance is not None and principal is not None:
            paid = instance.paid_amount
            if principal < paid:
                raise serializers.ValidationError(
                    {
                        "principal": (
                            f"مبلغ کل نمی‌تواند کمتر از مبلغ پرداخت‌شده "
                            f"({format_money(paid)}) باشد."
                        )
                    }
                )

        return attrs


class DebtPaymentWriteSerializer(serializers.ModelSerializer):
    """Record a payment against a debt."""

    class Meta:
        model = DebtPayment
        fields = ("id", "amount", "paid_on", "note", "account")
        read_only_fields = ("id",)

    def validate_amount(self, value):
        amount = quantize_money(to_decimal(value))
        if amount <= 0:
            raise serializers.ValidationError("مبلغ پرداخت باید بیشتر از صفر باشد.")
        return amount

    def validate_paid_on(self, value):
        """Allow a forward-dated payment, within a bounded horizon.

        A payment is normally a record of money that has already moved, but a
        scheduled instalment or a post-dated cheque is a real thing users want
        tracked. The bound catches a mistyped year without blocking planning.
        """
        from apps.transactions.serializers import FUTURE_HORIZON_DAYS

        if value > dt.date.today() + dt.timedelta(days=FUTURE_HORIZON_DAYS):
            raise serializers.ValidationError(
                f"تاریخ پرداخت نمی‌تواند بیش از {FUTURE_HORIZON_DAYS} روز در آینده باشد."
            )
        return value

    def validate_account(self, value):
        if value is None:
            return value
        request = self.context.get("request")
        if request and value.user_id != request.user.id:
            raise serializers.ValidationError("حساب انتخاب‌شده معتبر نیست.")
        return value

    def validate(self, attrs):
        debt = self.context.get("debt")
        if debt is None:
            raise serializers.ValidationError("بدهی مشخص نشده است.")

        amount = attrs.get("amount", getattr(self.instance, "amount", Decimal("0")))
        remaining = debt.remaining_amount

        # Overpayment is refused rather than silently absorbed: the balance
        # would otherwise go negative and the debt's status would be wrong.
        if amount > remaining:
            raise serializers.ValidationError(
                {
                    "amount": (
                        f"مبلغ پرداخت نمی‌تواند بیشتر از باقی‌مانده "
                        f"({format_money(remaining)}) باشد."
                    )
                }
            )

        return attrs

    @db_transaction.atomic
    def create(self, validated_data):
        debt = self.context["debt"]
        payment = DebtPayment.objects.create(debt=debt, **validated_data)
        _sync_settled_state(debt)
        return payment

    @db_transaction.atomic
    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        _sync_settled_state(instance.debt)
        return instance


def _sync_settled_state(debt: Debt) -> None:
    """Keep `settled_at` consistent with the actual balance.

    Called after any payment change. Setting the timestamp when the balance
    reaches zero (and clearing it if a payment is removed) is what makes the
    "settled" status trustworthy over time.
    """
    remaining = debt.remaining_amount

    if remaining <= 0 and debt.settled_at is None:
        debt.settled_at = timezone.now()
        debt.save(update_fields=["settled_at", "updated_at"])
    elif remaining > 0 and debt.settled_at is not None:
        debt.settled_at = None
        debt.save(update_fields=["settled_at", "updated_at"])


def debt_totals(user) -> dict:
    """Aggregate debt figures across a user's records.

    Computed in Python over prefetched payments rather than in SQL, because the
    derived `remaining_amount` depends on a per-debt subtraction that SQL would
    need a subquery to express — and the number of debts a person has is small.
    """
    debts = list(Debt.objects.for_user(user).prefetch_related("payments"))

    payable_total = Decimal("0.00")
    receivable_total = Decimal("0.00")
    payable_remaining = Decimal("0.00")
    receivable_remaining = Decimal("0.00")
    overdue_count = 0
    overdue_amount = Decimal("0.00")
    settled_count = 0

    for debt in debts:
        if debt.is_settled:
            settled_count += 1

        if debt.direction == DebtDirection.PAYABLE:
            payable_total += debt.principal
            payable_remaining += debt.remaining_amount
        else:
            receivable_total += debt.principal
            receivable_remaining += debt.remaining_amount

        if debt.is_overdue:
            overdue_count += 1
            overdue_amount += debt.remaining_amount

    return {
        "payable_total": str(quantize_money(payable_total)),
        "receivable_total": str(quantize_money(receivable_total)),
        "payable_remaining": str(quantize_money(payable_remaining)),
        "receivable_remaining": str(quantize_money(receivable_remaining)),
        "net_position": str(quantize_money(receivable_remaining - payable_remaining)),
        "overdue_count": overdue_count,
        "overdue_amount": str(quantize_money(overdue_amount)),
        "settled_count": settled_count,
        "total_count": len(debts),
        "open_count": len(debts) - settled_count,
        # Display strings so the client renders identical text.
        "payable_total_display": format_money(payable_total),
        "receivable_total_display": format_money(receivable_total),
        "payable_remaining_display": format_money(payable_remaining),
        "receivable_remaining_display": format_money(receivable_remaining),
        "net_position_display": format_money(receivable_remaining - payable_remaining),
        "overdue_amount_display": format_money(overdue_amount),
    }
