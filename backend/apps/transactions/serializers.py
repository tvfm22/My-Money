"""Transaction serializers.

Validation policy
-----------------
The serializer is where financial correctness is enforced on the way in:

*   `amount` must be strictly positive (direction is `transaction_type`).
*   The category must belong to the requesting user, and its `kind` must match
    the transaction direction — an expense cannot reference an income category.
*   The account, if given, must belong to the requesting user.
*   Tags are resolved-or-created, always scoped to the requesting user.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction as db_transaction
from rest_framework import serializers

from apps.categories.models import Category, CategoryKind
from apps.categories.serializers import CategoryPickerSerializer
from apps.core.fields import JalaliDateField
from apps.core.jalali import format_jalali, format_money
from apps.core.money import quantize_money, to_decimal

from .models import Tag, Transaction, TransactionType

MAX_AMOUNT = Decimal("999999999999999.99")

# How far ahead a transaction may be dated. A year covers the forward-looking
# cases this app now supports (post-dated cheques, next month's rent, a known
# annual charge) while still catching a mistyped century. Kept in days so it
# stays independent of the calendar in use.
FUTURE_HORIZON_DAYS = 366


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ("id", "name", "color")
        read_only_fields = ("id",)


class TransactionSerializer(serializers.ModelSerializer):
    """Read serializer.

    Carries pre-formatted display strings alongside raw values. Formatting on
    the server guarantees that the Persian digits, thousands separators and
    Jalali date shown in the API response match what the backend used for its
    own calculations, so the two can never disagree.
    """

    amount = serializers.SerializerMethodField()
    signed_amount = serializers.SerializerMethodField()
    amount_display = serializers.SerializerMethodField()

    category_detail = CategoryPickerSerializer(source="category", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True, default=None)
    account_icon = serializers.CharField(source="account.icon", read_only=True, default=None)
    tags = TagSerializer(many=True, read_only=True)

    transaction_type_label = serializers.CharField(
        source="get_transaction_type_display", read_only=True
    )
    # The property, not `get_spending_type_display`, so the "blank on income"
    # rule lives in one place — the model — rather than being re-derived here.
    # No `source`: the property is already named the same as the field, and DRF
    # rejects the redundancy.
    spending_type_label = serializers.CharField(read_only=True)
    date_display = serializers.SerializerMethodField()
    date_short = serializers.SerializerMethodField()
    jalali_date = serializers.SerializerMethodField()
    title = serializers.CharField(source="display_title", read_only=True)

    class Meta:
        model = Transaction
        fields = (
            "id",
            "transaction_type",
            "transaction_type_label",
            "spending_type",
            "spending_type_label",
            "amount",
            "signed_amount",
            "amount_display",
            "category",
            "category_detail",
            "account",
            "account_name",
            "account_icon",
            "occurred_on",
            "jalali_date",
            "date_display",
            "date_short",
            "description",
            "title",
            "note",
            "tags",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def get_amount(self, obj) -> str:
        # Serialized as a string so JavaScript never receives a float for money.
        return str(quantize_money(obj.amount))

    def get_signed_amount(self, obj) -> str:
        return str(quantize_money(obj.signed_amount))

    def get_amount_display(self, obj) -> str:
        return format_money(obj.amount)

    def get_date_display(self, obj) -> str:
        return format_jalali(obj.occurred_on, style="full")

    def get_date_short(self, obj) -> str:
        return format_jalali(obj.occurred_on, style="short")

    def get_jalali_date(self, obj) -> str:
        return format_jalali(obj.occurred_on, style="numeric")


class TransactionWriteSerializer(serializers.ModelSerializer):
    """Create/update serializer.

    Accepts `tag_names` (a list of strings) as a convenience for the quick-entry
    form, resolving each to an existing Tag or creating one.
    """

    tag_names = serializers.ListField(
        child=serializers.CharField(max_length=40),
        required=False,
        write_only=True,
    )
    tag_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        write_only=True,
    )

    # Accepts Jalali (۱۴۰۵/۰۶/۲۹, 1405-06-29) as well as Gregorian ISO, so the
    # Jalali date picker can post what it shows without a client-side
    # conversion step.
    occurred_on = JalaliDateField()

    class Meta:
        model = Transaction
        fields = (
            "id",
            "transaction_type",
            "spending_type",
            "amount",
            "category",
            "account",
            "occurred_on",
            "description",
            "note",
            "tag_names",
            "tag_ids",
        )
        read_only_fields = ("id",)

    # ------------------------------------------------------------------
    # Field validation
    # ------------------------------------------------------------------

    def validate_amount(self, value):
        amount = quantize_money(to_decimal(value))
        if amount <= 0:
            raise serializers.ValidationError("مبلغ باید بیشتر از صفر باشد.")
        if amount > MAX_AMOUNT:
            raise serializers.ValidationError("مبلغ وارد شده بیش از حد بزرگ است.")
        return amount

    def validate_description(self, value):
        return (value or "").strip()

    def validate_note(self, value):
        return (value or "").strip()

    def validate_category(self, value):
        request = self.context.get("request")
        if request and value.user_id != request.user.id:
            # Do not confirm whether the category exists at all.
            raise serializers.ValidationError("دسته‌بندی انتخاب‌شده معتبر نیست.")
        return value

    def validate_account(self, value):
        if value is None:
            return value
        request = self.context.get("request")
        if request and value.user_id != request.user.id:
            raise serializers.ValidationError("حساب انتخاب‌شده معتبر نیست.")
        return value

    def validate_occurred_on(self, value):
        """Allow a future date, but keep it within a sane horizon.

        A transaction is usually a record of something that happened, and an
        accidental future date used to be rejected outright. But some entries
        are genuinely forward-looking: a post-dated cheque, a rent payment
        scheduled for the first of next month, a recurring charge known in
        advance. Refusing those forced users to either lie about the date or
        keep the commitment outside the app entirely.

        The rule is now a bound rather than a ban. Aggregations are already
        range-filtered (see ``spent_by_category``), so a future-dated row lands
        in the month it is dated and does *not* inflate the current month's
        totals or distort today's budget analysis. The horizon exists so a
        mistyped year — 1405 entered as 1450 — is still caught.
        """
        import datetime as dt

        if value > dt.date.today() + dt.timedelta(days=FUTURE_HORIZON_DAYS):
            raise serializers.ValidationError(
                f"تاریخ تراکنش نمی‌تواند بیش از {FUTURE_HORIZON_DAYS} روز در آینده باشد."
            )
        return value

    def validate(self, attrs):
        instance = self.instance

        transaction_type = attrs.get(
            "transaction_type", getattr(instance, "transaction_type", None)
        )
        category = attrs.get("category", getattr(instance, "category", None))

        # Direction and category kind must agree. This is the check that stops
        # an expense being filed under "حقوق".
        if category is not None and transaction_type is not None:
            expected_kind = (
                CategoryKind.EXPENSE
                if transaction_type == TransactionType.EXPENSE
                else CategoryKind.INCOME
            )
            if category.kind != expected_kind:
                label = "هزینه" if transaction_type == TransactionType.EXPENSE else "درآمد"
                raise serializers.ValidationError(
                    {
                        "category": (
                            f"برای ثبت {label} باید یک دسته‌بندی "
                            f"{'هزینه' if transaction_type == TransactionType.EXPENSE else 'درآمد'} انتخاب کنید."
                        )
                    }
                )

        # A transaction must carry an explicit explanation if there is no
        # description: an unlabelled row is effectively unfindable later.
        description = attrs.get("description", getattr(instance, "description", ""))
        if not str(description or "").strip() and not attrs.get("note"):
            # Not an error — the category alone is often enough. Only warn by
            # normalizing the field so the display helper has something sane.
            attrs["description"] = ""

        # A classification only means something for an expense. Rejecting it on
        # income keeps the field honest instead of silently discarding whatever
        # the client sent — a client that sends it for income has a bug, and a
        # silent drop is how that bug survives to production.
        #
        # Note there is deliberately no default here for a *missing* value on an
        # expense: `Transaction.save()` supplies `flexible`, and — crucially —
        # only when the row has no classification yet. A PATCH that omits the
        # field must leave the stored value alone.
        if transaction_type == TransactionType.INCOME and attrs.get("spending_type"):
            raise serializers.ValidationError(
                {"spending_type": "برای درآمد، نوع هزینه معنا ندارد."}
            )

        return attrs

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _resolve_tags(self, validated_data, user):
        """Turn `tag_names` / `tag_ids` into a list of the user's Tags."""
        tags: list[Tag] = []

        ids = validated_data.pop("tag_ids", None) or []
        if ids:
            # Filter by user so a guessed ID cannot attach someone else's tag.
            tags.extend(list(Tag.objects.filter(user=user, id__in=ids)))

        names = validated_data.pop("tag_names", None) or []
        if names:
            existing = {
                tag.name: tag
                for tag in Tag.objects.filter(user=user, name__in=[n.strip() for n in names if n.strip()])
            }
            for raw in names:
                name = raw.strip()
                if not name:
                    continue
                tag = existing.get(name)
                if tag is None:
                    tag = Tag.objects.create(user=user, name=name)
                    existing[name] = tag
                tags.append(tag)

        # De-duplicate while preserving order.
        seen: set[int] = set()
        unique: list[Tag] = []
        for tag in tags:
            if tag.pk not in seen:
                seen.add(tag.pk)
                unique.append(tag)
        return unique

    @db_transaction.atomic
    def create(self, validated_data):
        user = self.context["request"].user
        tags = self._resolve_tags(validated_data, user)

        instance = Transaction.objects.create(user=user, **validated_data)
        if tags:
            instance.tags.set(tags)
        return instance

    @db_transaction.atomic
    def update(self, instance, validated_data):
        user = self.context["request"].user
        tags = self._resolve_tags(validated_data, user)

        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()

        if tags:
            instance.tags.set(tags)
        return instance


class TransactionBulkCreateSerializer(serializers.Serializer):
    """Payload for creating several transactions at once (import / quick add)."""

    transactions = TransactionWriteSerializer(many=True)

    def validate_transactions(self, value):
        if not value:
            raise serializers.ValidationError("حداقل یک تراکنش لازم است.")
        if len(value) > 200:
            raise serializers.ValidationError("در هر درخواست حداکثر ۲۰۰ تراکنش قابل ثبت است.")
        return value
