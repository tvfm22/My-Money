"""Budget serializers."""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.categories.models import Category, CategoryKind
from apps.core.money import quantize_money, to_decimal

from .models import Budget, BudgetItem


class BudgetItemSerializer(serializers.ModelSerializer):
    """Read serializer for a budget line, including live spending.

    `spent`, `remaining` and the percentage fields are injected by the view from
    the analysis service. They are declared here as read-only so the client gets
    one consistent object shape whether it came from the list or the analysis
    endpoint.
    """

    category_name = serializers.CharField(source="category.name", read_only=True)
    category_icon = serializers.CharField(source="category.icon", read_only=True)
    category_color = serializers.CharField(source="category.color", read_only=True)
    category_full_path = serializers.CharField(source="category.full_path", read_only=True)

    # Defaults make the serializer valid even when no analysis was attached.
    spent = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True, default=Decimal("0.00"))
    remaining = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True, default=Decimal("0.00"))
    consumed_percent = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True, default=Decimal("0.00"))
    status = serializers.CharField(read_only=True, default="safe")
    status_label = serializers.CharField(read_only=True, default="")
    message = serializers.CharField(read_only=True, default="")

    class Meta:
        model = BudgetItem
        fields = (
            "id",
            "category",
            "category_name",
            "category_icon",
            "category_color",
            "category_full_path",
            "amount",
            "is_essential",
            "note",
            "spent",
            "remaining",
            "consumed_percent",
            "status",
            "status_label",
            "message",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class BudgetItemWriteSerializer(serializers.ModelSerializer):
    """Create/update a budget line.

    Accepts `category_id` as an alias for `category` because the client's
    category picker naturally works with ids.
    """

    category_id = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = BudgetItem
        fields = ("id", "category", "category_id", "amount", "is_essential", "note")
        read_only_fields = ("id",)
        extra_kwargs = {"category": {"required": False}}

    def validate_amount(self, value):
        amount = quantize_money(to_decimal(value))
        if amount < 0:
            raise serializers.ValidationError("مبلغ بودجه نمی‌تواند منفی باشد.")
        if amount > Decimal("999999999999999.99"):
            raise serializers.ValidationError("مبلغ وارد شده بیش از حد بزرگ است.")
        return amount

    def validate(self, attrs):
        request = self.context["request"]
        user = request.user

        # Resolve the category from either field name.
        category = attrs.get("category")
        category_id = attrs.pop("category_id", None)
        if category is None and category_id is not None:
            category = Category.objects.filter(pk=category_id, user=user).first()
            if category is None:
                raise serializers.ValidationError(
                    {"category": "دسته‌بندی انتخاب‌شده معتبر نیست."}
                )
            attrs["category"] = category

        instance = self.instance
        if category is None and instance is None:
            raise serializers.ValidationError({"category": "دسته‌بندی الزامی است."})
        if category is None:
            category = instance.category

        # Only expense categories can be budgeted.
        if category.kind != CategoryKind.EXPENSE:
            raise serializers.ValidationError(
                {"category": "فقط دسته‌بندی‌های هزینه قابل بودجه‌بندی هستند."}
            )

        # The budget this item belongs to must be the user's. `budget` is
        # supplied by the view via serializer context, not by the client.
        budget = self.context.get("budget") or getattr(instance, "budget", None)
        if budget is None:
            raise serializers.ValidationError("بودجه مشخص نشده است.")

        # No duplicate category within one month's budget.
        duplicates = BudgetItem.objects.filter(budget=budget, category=category)
        if instance is not None:
            duplicates = duplicates.exclude(pk=instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError(
                {"category": "برای این دسته‌بندی در این ماه بودجه ثبت شده است."}
            )

        return attrs

    def create(self, validated_data):
        budget = self.context["budget"]
        return BudgetItem.objects.create(budget=budget, **validated_data)


class BudgetSerializer(serializers.ModelSerializer):
    """Read serializer for a budget, with items and plan totals."""

    month_name = serializers.CharField(read_only=True)
    label = serializers.CharField(read_only=True)
    items = BudgetItemSerializer(many=True, read_only=True)

    allocated_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    committed_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    flexible_budget = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    is_oversubscribed = serializers.BooleanField(read_only=True)

    class Meta:
        model = Budget
        fields = (
            "id",
            "year",
            "month",
            "month_name",
            "label",
            "expected_income",
            "savings_target",
            "investment_target",
            "debt_payment_target",
            "note",
            "is_active",
            "items",
            "allocated_total",
            "committed_total",
            "flexible_budget",
            "is_oversubscribed",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class BudgetWriteSerializer(serializers.ModelSerializer):
    """Create/update a monthly budget's plan figures.

    Accepts `month` as either a Jalali year/month pair or a '1405-06' string via
    the optional `month_key` field, which is what a month picker naturally
    produces.
    """

    month_key = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Budget
        fields = (
            "id",
            "year",
            "month",
            "month_key",
            "expected_income",
            "savings_target",
            "investment_target",
            "debt_payment_target",
            "note",
            "is_active",
        )
        read_only_fields = ("id",)
        extra_kwargs = {
            "year": {"required": False},
            "month": {"required": False},
        }

    def _clean_amount(self, field_name, value):
        amount = quantize_money(to_decimal(value))
        if amount < 0:
            raise serializers.ValidationError(f"{field_name} نمی‌تواند منفی باشد.")
        return amount

    def validate_expected_income(self, value):
        return self._clean_amount("درآمد پیش‌بینی‌شده", value)

    def validate_savings_target(self, value):
        return self._clean_amount("پس‌انداز هدف", value)

    def validate_investment_target(self, value):
        return self._clean_amount("سرمایه‌گذاری هدف", value)

    def validate_debt_payment_target(self, value):
        return self._clean_amount("بازپرداخت بدهی", value)

    def validate_month(self, value):
        if not 1 <= int(value) <= 12:
            raise serializers.ValidationError("ماه باید بین ۱ و ۱۲ باشد.")
        return int(value)

    def validate_year(self, value):
        if not 1300 <= int(value) <= 1500:
            raise serializers.ValidationError("سال باید بین ۱۳۰۰ و ۱۵۰۰ باشد.")
        return int(value)

    def validate(self, attrs):
        from apps.core.jalali import current_jalali_month, to_latin_digits

        request = self.context["request"]
        user = request.user
        instance = self.instance

        # Resolve year/month from whichever representation was supplied.
        month_key = attrs.pop("month_key", None)
        if month_key:
            raw = to_latin_digits(str(month_key)).replace("/", "-")
            parts = raw.split("-")
            if len(parts) == 2:
                try:
                    attrs["year"] = int(parts[0])
                    attrs["month"] = int(parts[1])
                except ValueError:
                    raise serializers.ValidationError(
                        {"month_key": "قالب ماه نامعتبر است. نمونه درست: ۱۴۰۵-۰۶"}
                    ) from None
            else:
                raise serializers.ValidationError(
                    {"month_key": "قالب ماه نامعتبر است. نمونه درست: ۱۴۰۵-۰۶"}
                )
        elif instance is None and ("year" not in attrs or "month" not in attrs):
            # Default to the current Jalali month when the client omits it.
            year, month = current_jalali_month()
            attrs.setdefault("year", year)
            attrs.setdefault("month", month)

        year = attrs.get("year", getattr(instance, "year", None))
        month = attrs.get("month", getattr(instance, "month", None))

        if year is not None and not 1300 <= int(year) <= 1500:
            raise serializers.ValidationError({"year": "سال باید بین ۱۳۰۰ و ۱۵۰۰ باشد."})
        if month is not None and not 1 <= int(month) <= 12:
            raise serializers.ValidationError({"month": "ماه باید بین ۱ و ۱۲ باشد."})

        # One budget per month per user.
        if year is not None and month is not None:
            duplicates = Budget.objects.filter(user=user, year=year, month=month)
            if instance is not None:
                duplicates = duplicates.exclude(pk=instance.pk)
            if duplicates.exists():
                raise serializers.ValidationError(
                    {"month_key": "برای این ماه قبلاً بودجه ساخته شده است."}
                )

        return attrs


class MonthlyPlanSerializer(serializers.Serializer):
    """Input for the monthly planning screen (spec section 12).

    Lets the client set the whole plan in one request: the income envelope plus
    a set of category allocations. Existing allocations not mentioned are left
    untouched unless `replace_allocations` is true.
    """

    year = serializers.IntegerField(min_value=1300, max_value=1500)
    month = serializers.IntegerField(min_value=1, max_value=12)

    expected_income = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, default=Decimal("0.00")
    )
    savings_target = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, default=Decimal("0.00")
    )
    investment_target = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, default=Decimal("0.00")
    )
    debt_payment_target = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, default=Decimal("0.00")
    )

    allocations = serializers.ListField(
        child=serializers.DictField(), required=False, default=list
    )

    replace_allocations = serializers.BooleanField(default=False)

    def validate_allocations(self, value):
        """Each entry must be {'category': <id>, 'amount': <decimal>}."""
        cleaned = []
        for index, entry in enumerate(value):
            if "category" not in entry and "category_id" not in entry:
                raise serializers.ValidationError(
                    f"ردیف {index + 1}: شناسه دسته‌بندی مشخص نشده است."
                )
            category_id = entry.get("category") or entry.get("category_id")
            try:
                category_id = int(category_id)
            except (TypeError, ValueError):
                raise serializers.ValidationError(
                    f"ردیف {index + 1}: شناسه دسته‌بندی نامعتبر است."
                ) from None

            try:
                amount = quantize_money(to_decimal(entry.get("amount", 0)))
            except ValueError:
                raise serializers.ValidationError(
                    f"ردیف {index + 1}: مبلغ نامعتبر است."
                ) from None

            if amount < 0:
                raise serializers.ValidationError(
                    f"ردیف {index + 1}: مبلغ نمی‌تواند منفی باشد."
                )

            cleaned.append(
                {
                    "category_id": category_id,
                    "amount": amount,
                    # `None` means "the client did not say", which is different
                    # from "the client said no". Collapsing the two to False —
                    # which is what `bool(entry.get(...))` did — meant any save
                    # that omitted the flag silently cleared it, so a line the
                    # user had marked non-negotiable became flexible again on the
                    # next edit. The view leaves the stored value alone when this
                    # is None.
                    "is_essential": (
                        bool(entry["is_essential"])
                        if entry.get("is_essential") is not None
                        else None
                    ),
                    "note": str(entry.get("note", ""))[:200],
                }
            )
        return cleaned
