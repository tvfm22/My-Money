"""Serializers for SMS import.

Two things are deliberately shaped differently from the rest of the API:

*   ``raw_text`` is always sent. The review screen shows the original message
    next to the fields the parser filled in, because that is the only way a user
    can tell whether "۹۸۷,۶۵۴ ریال" was read as the amount or as the balance.
*   ``confidence`` is sent three ways — the raw score, a formatted percentage,
    and a Persian label — so the client never has to decide what 0.73 *means*.
    Thresholds are a server-side judgement, not a display detail.
"""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.accounts.models import Account
from apps.categories.models import Category, CategoryKind
from apps.categories.serializers import CategoryPickerSerializer
from apps.core.fields import JalaliDateField
from apps.core.jalali import format_jalali, format_money, format_percent
from apps.core.money import quantize_money

from .models import SmsImportBatch, SmsImportItem
from .parser import LOW_CONFIDENCE

# Where the confidence label changes meaning. HIGH is "no reason to look", LOW is
# "check this before importing".
HIGH_CONFIDENCE = Decimal("0.85")

# Statuses a client may set by hand. `imported` is reached only by committing, and
# `duplicate` only by the staging pass — letting a client write either would let
# it claim a row was imported when no transaction exists.
CLIENT_SETTABLE_STATUSES = ("pending", "skipped")


class SmsImportItemSerializer(serializers.ModelSerializer):
    """A staged item: the parse result, plus the user's decisions."""

    amount = serializers.SerializerMethodField()
    amount_display = serializers.SerializerMethodField()
    balance_after = serializers.SerializerMethodField()
    balance_display = serializers.SerializerMethodField()

    confidence = serializers.SerializerMethodField()
    confidence_percent_display = serializers.SerializerMethodField()
    confidence_label = serializers.SerializerMethodField()
    field_confidence = serializers.JSONField(read_only=True)

    category_detail = CategoryPickerSerializer(source="category", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True, default=None)

    occurred_on = JalaliDateField(allow_null=True, required=False)
    date_display = serializers.SerializerMethodField()
    date_assumed = serializers.SerializerMethodField()

    direction_label = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    is_ready = serializers.BooleanField(read_only=True)

    class Meta:
        model = SmsImportItem
        fields = (
            "id",
            # --- what arrived -------------------------------------------------
            "raw_text",
            "sender",
            "bank",
            "bank_label",
            "is_transaction",
            "noise_kind",
            "card_last4",
            "merchant",
            # --- what was parsed ---------------------------------------------
            "direction",
            "direction_label",
            "direction_pattern",
            "amount",
            "amount_display",
            "amount_unit",
            "amount_unit_assumed",
            "balance_after",
            "balance_display",
            "balance_label",
            "occurred_on",
            "date_display",
            "date_assumed",
            "date_source",
            "confidence",
            "confidence_percent_display",
            "confidence_label",
            "field_confidence",
            "warnings",
            # --- what the user decided ---------------------------------------
            "category",
            "category_detail",
            "account",
            "account_name",
            "spending_type",
            "description",
            "note",
            "status",
            "status_label",
            "transaction",
            "is_ready",
        )
        read_only_fields = ("id", "transaction")

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def get_amount(self, obj: SmsImportItem):
        return None if obj.amount is None else str(obj.amount)

    def get_amount_display(self, obj: SmsImportItem):
        return None if obj.amount is None else format_money(obj.amount)

    def get_balance_after(self, obj: SmsImportItem):
        """``None`` when the message printed no balance — never ``"0.00"``."""
        return None if obj.balance_after is None else str(obj.balance_after)

    def get_balance_display(self, obj: SmsImportItem):
        return None if obj.balance_after is None else format_money(obj.balance_after)

    def get_confidence(self, obj: SmsImportItem) -> float:
        return float(obj.confidence or 0)

    def get_confidence_percent_display(self, obj: SmsImportItem) -> str:
        return format_percent(Decimal(obj.confidence or 0) * 100)

    def get_confidence_label(self, obj: SmsImportItem) -> str:
        score = Decimal(obj.confidence or 0)
        if score >= HIGH_CONFIDENCE:
            return "اطمینان بالا"
        if score >= LOW_CONFIDENCE:
            return "قابل بررسی"
        return "اطمینان کم"

    def get_date_display(self, obj: SmsImportItem) -> str | None:
        if obj.occurred_on is None:
            return None
        return format_jalali(obj.occurred_on)

    def get_date_assumed(self, obj: SmsImportItem) -> bool:
        """True when the date was not read from the message."""
        return obj.date_source == "assumed" or obj.occurred_on is None

    def get_direction_label(self, obj: SmsImportItem) -> str:
        for value, label in obj._meta.get_field("direction").choices:
            if value == obj.direction:
                return label
        return ""

    # ------------------------------------------------------------------
    # Write validation
    # ------------------------------------------------------------------

    def validate_amount(self, value):
        """The user may correct a mis-read figure, but not to zero or less."""
        if value is None:
            return None
        if value <= 0:
            raise serializers.ValidationError("مبلغ باید بیشتر از صفر باشد.")
        return quantize_money(value)

    def validate_status(self, value):
        if value not in CLIENT_SETTABLE_STATUSES:
            raise serializers.ValidationError(
                "تنها می‌توانید قلم را «در انتظار بررسی» یا «رد شده» بگذارید."
            )
        return value

    def validate_category(self, value):
        if value is None:
            return None
        request = self.context.get("request")
        if request and value.user_id != request.user.id:
            raise serializers.ValidationError("دسته‌بندی انتخابی معتبر نیست.")
        return value

    def validate_account(self, value):
        if value is None:
            return None
        request = self.context.get("request")
        if request and value.user_id != request.user.id:
            raise serializers.ValidationError("حساب انتخابی معتبر نیست.")
        return value

    def validate(self, attrs):
        instance = self.instance
        direction = attrs.get("direction", getattr(instance, "direction", "") or "")
        category = attrs.get("category", getattr(instance, "category", None))

        # The category's kind must match the direction, exactly as the
        # transaction serializer insists. Without this, flipping a row from
        # expense to income would commit it against an expense category.
        if category is not None and direction:
            expected = (
                CategoryKind.INCOME if direction == "income" else CategoryKind.EXPENSE
            )
            if category.kind != expected:
                raise serializers.ValidationError(
                    {"category": "دسته‌بندی با جهت این تراکنش هم‌خوان نیست."}
                )

        if direction == "income":
            # Income has no classification; clearing it here matches
            # `Transaction.save()`, which would clear it on commit anyway.
            attrs["spending_type"] = ""
        elif "spending_type" not in attrs and instance is None:
            attrs["spending_type"] = ""

        return attrs


# --------------------------------------------------------------------------
# Batches
# --------------------------------------------------------------------------


def _counts(items) -> dict:
    """Per-status totals, computed from the already-loaded items."""
    totals = {"total": 0, "pending": 0, "imported": 0, "skipped": 0, "duplicate": 0, "noise": 0}
    for item in items:
        totals["total"] += 1
        if not item.is_transaction:
            totals["noise"] += 1
        totals[item.status] = totals.get(item.status, 0) + 1
    return totals


class SmsImportBatchSummarySerializer(serializers.ModelSerializer):
    """A batch without its items — for the history list."""

    period_label = serializers.CharField(read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True, default=None)
    counts = serializers.SerializerMethodField()

    class Meta:
        model = SmsImportBatch
        fields = (
            "id",
            "period_year",
            "period_month",
            "period_label",
            "source_label",
            "account",
            "account_name",
            "status",
            "status_label",
            "note",
            "counts",
            "created_at",
            "updated_at",
            "committed_at",
        )
        read_only_fields = ("id", "status", "committed_at", "created_at", "updated_at")

    def get_counts(self, obj: SmsImportBatch) -> dict:
        return _counts(obj.items.all())

    def validate_account(self, value):
        # The update path (PATCH /batches/{id}/) re-points the batch — and the
        # reconciliation actions write `opening_balance` through that account.
        # Without this, a batch could be pointed at another user's account.
        if value is None:
            return None
        request = self.context.get("request")
        if request and value.user_id != request.user.id:
            raise serializers.ValidationError("حساب انتخابی معتبر نیست.")
        return value


class SmsImportBatchSerializer(SmsImportBatchSummarySerializer):
    """A batch with every item — what the review screen loads."""

    items = SmsImportItemSerializer(many=True, read_only=True)

    class Meta(SmsImportBatchSummarySerializer.Meta):
        fields = SmsImportBatchSummarySerializer.Meta.fields + ("items",)
        read_only_fields = SmsImportBatchSummarySerializer.Meta.read_only_fields


# --------------------------------------------------------------------------
# Requests
# --------------------------------------------------------------------------


class SmsMessageSerializer(serializers.Serializer):
    """One message supplied explicitly, rather than parsed out of a blob."""

    sender = serializers.CharField(required=False, allow_blank=True, max_length=80)
    body = serializers.CharField(trim_whitespace=False)


class SmsParseRequestSerializer(serializers.Serializer):
    """Payload for reading messages: a pasted blob, or explicit messages."""

    text = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)
    messages = SmsMessageSerializer(many=True, required=False)
    source_label = serializers.CharField(required=False, allow_blank=True, max_length=120)
    period_year = serializers.IntegerField(required=False, min_value=1300, max_value=1600)
    period_month = serializers.IntegerField(required=False, min_value=1, max_value=12)
    account = serializers.PrimaryKeyRelatedField(
        queryset=Account.objects.all(), required=False, allow_null=True
    )

    def validate_account(self, value):
        if value is None:
            return None
        request = self.context.get("request")
        if request and value.user_id != request.user.id:
            raise serializers.ValidationError("حساب انتخابی معتبر نیست.")
        return value

    def validate(self, attrs):
        has_text = bool((attrs.get("text") or "").strip())
        has_messages = bool(attrs.get("messages"))

        if not has_text and not has_messages:
            raise serializers.ValidationError(
                {"text": "متنی برای خواندن ارسال نشده است. پیامک‌ها را بچسبانید یا فایل بفرستید."}
            )

        # A period is either fully specified or not specified at all: half of one
        # would silently default to the previous month and file the messages
        # under a month the client did not ask for.
        year, month = attrs.get("period_year"), attrs.get("period_month")
        if (year is None) != (month is None):
            raise serializers.ValidationError(
                {"period_month": "سال و ماه را با هم بفرستید."}
            )

        return attrs


class SmsCommitRequestSerializer(serializers.Serializer):
    """Payload for committing: which items to write (all pending by default)."""

    item_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, allow_null=True
    )


class SmsAutoImportToggleSerializer(serializers.Serializer):
    """Payload for turning automatic reading on or off.

    A single explicit boolean. The field is required rather than defaulted,
    because "turn it on" and "say nothing" must not be the same request — a
    defaulted value would let a client flip the switch by omission.
    """

    enabled = serializers.BooleanField()


class SmsSyncRequestSerializer(SmsParseRequestSerializer):
    """Payload for the check: the same shape as reading, minus the requirement.

    Reading requires text (there is nothing to read otherwise). The check does
    not: with no text it reports the backlog, which is what the automatic pass
    on opening the screen sends.
    """

    def validate(self, attrs):
        year, month = attrs.get("period_year"), attrs.get("period_month")
        if (year is None) != (month is None):
            raise serializers.ValidationError({"period_month": "سال و ماه را با هم بفرستید."})
        return attrs


class SmsReminderDismissSerializer(serializers.Serializer):
    period_year = serializers.IntegerField(min_value=1300, max_value=1600)
    period_month = serializers.IntegerField(min_value=1, max_value=12)


class SmsBulkUpdateRequestSerializer(serializers.Serializer):
    """Apply one decision to a selection of staged items."""

    item_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), allow_empty=False
    )
    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), required=False, allow_null=True
    )
    account = serializers.PrimaryKeyRelatedField(
        queryset=Account.objects.all(), required=False, allow_null=True
    )
    spending_type = serializers.ChoiceField(
        choices=[("essential", "ضروری"), ("flexible", "انعطاف‌پذیر"), ("wasted", "غیرضروری")],
        required=False,
    )
    status = serializers.ChoiceField(choices=CLIENT_SETTABLE_STATUSES, required=False)

    def validate_category(self, value):
        if value is None:
            return None
        request = self.context.get("request")
        if request and value.user_id != request.user.id:
            raise serializers.ValidationError("دسته‌بندی انتخابی معتبر نیست.")
        return value

    def validate_account(self, value):
        if value is None:
            return None
        request = self.context.get("request")
        if request and value.user_id != request.user.id:
            raise serializers.ValidationError("حساب انتخابی معتبر نیست.")
        return value

    def validate(self, attrs):
        if not any(
            key in attrs for key in ("category", "account", "spending_type", "status")
        ):
            raise serializers.ValidationError(
                {"category": "چیزی برای اعمال انتخاب نشده است."}
            )
        return attrs



