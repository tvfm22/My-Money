"""Account serializers, including a totals-annotated list variant."""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.core.jalali import format_money, format_percent
from apps.core.money import quantize_money, safe_divide

from .models import Account, AccountType


class AccountSerializer(serializers.ModelSerializer):
    """Read serializer.

    Balance fields come from annotations when present (set by the viewset's
    queryset) and fall back to the model's derived properties otherwise. This
    keeps N+1 queries out of the list endpoint while still working for a
    single-object retrieve.
    """

    account_type_label = serializers.CharField(
        source="get_account_type_display", read_only=True
    )
    current_balance = serializers.SerializerMethodField()
    income_total = serializers.SerializerMethodField()
    expense_total = serializers.SerializerMethodField()
    balance_display = serializers.SerializerMethodField()
    transactions_count = serializers.SerializerMethodField()

    class Meta:
        model = Account
        fields = (
            "id",
            "name",
            "account_type",
            "account_type_label",
            "opening_balance",
            "current_balance",
            "income_total",
            "expense_total",
            "balance_display",
            "transactions_count",
            "institution",
            "color",
            "icon",
            "include_in_total",
            "is_active",
            "sort_order",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def _annotated(self, obj, attr: str):
        return getattr(obj, attr, None)

    def get_income_total(self, obj) -> str:
        value = self._annotated(obj, "income_total_annotated")
        if value is None:
            value = obj.income_total
        return str(quantize_money(value))

    def get_expense_total(self, obj) -> str:
        value = self._annotated(obj, "expense_total_annotated")
        if value is None:
            value = obj.expense_total
        return str(quantize_money(value))

    def get_current_balance(self, obj) -> str:
        annotated = self._annotated(obj, "current_balance_annotated")
        if annotated is not None:
            return str(quantize_money(annotated))
        return str(quantize_money(obj.current_balance))

    def get_balance_display(self, obj) -> str:
        annotated = self._annotated(obj, "current_balance_annotated")
        value = annotated if annotated is not None else obj.current_balance
        return format_money(quantize_money(value))

    def get_transactions_count(self, obj) -> int:
        annotated = self._annotated(obj, "transactions_count")
        if annotated is not None:
            return int(annotated)
        return obj.transactions.count()


class AccountWriteSerializer(serializers.ModelSerializer):
    """Create/update serializer."""

    class Meta:
        model = Account
        fields = (
            "id",
            "name",
            "account_type",
            "opening_balance",
            "institution",
            "color",
            "icon",
            "include_in_total",
            "is_active",
            "sort_order",
        )
        read_only_fields = ("id",)

    def validate_name(self, value):
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("نام حساب نمی‌تواند خالی باشد.")
        return cleaned

    def validate_opening_balance(self, value):
        # Negative opening balances are legitimate for a credit card, but the
        # magnitude should still be sane.
        if abs(value) > Decimal("999999999999999"):
            raise serializers.ValidationError("مبلغ موجودی اولیه بیش از حد بزرگ است.")
        return quantize_money(value)

    def validate(self, attrs):
        request = self.context["request"]
        user = request.user
        instance = self.instance

        name = attrs.get("name", getattr(instance, "name", ""))

        duplicates = Account.objects.filter(user=user, name=name)
        if instance is not None:
            duplicates = duplicates.exclude(pk=instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError(
                {"name": "حسابی با این نام قبلاً ساخته شده است."}
            )

        return attrs


class AccountPickerSerializer(serializers.ModelSerializer):
    """Compact list for transaction forms."""

    account_type_label = serializers.CharField(
        source="get_account_type_display", read_only=True
    )
    current_balance = serializers.SerializerMethodField()

    class Meta:
        model = Account
        fields = ("id", "name", "account_type", "account_type_label", "icon", "color", "current_balance")

    def get_current_balance(self, obj) -> str:
        annotated = getattr(obj, "current_balance_annotated", None)
        value = annotated if annotated is not None else obj.current_balance
        return str(quantize_money(value))
