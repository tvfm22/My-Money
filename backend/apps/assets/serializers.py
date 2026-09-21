"""Asset serializers."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from rest_framework import serializers

from apps.core.jalali import format_jalali, format_money, format_percent
from apps.core.money import percentage, quantize_money, to_decimal

from .models import Asset, AssetType, AssetValuation


class AssetValuationSerializer(serializers.ModelSerializer):
    valued_on_display = serializers.SerializerMethodField()
    value_display = serializers.SerializerMethodField()

    class Meta:
        model = AssetValuation
        fields = (
            "id",
            "value",
            "value_display",
            "valued_on",
            "valued_on_display",
            "note",
            "created_at",
        )
        read_only_fields = ("id", "created_at")

    def get_valued_on_display(self, obj) -> str:
        return format_jalali(obj.valued_on, style="short")

    def get_value_display(self, obj) -> str:
        return format_money(obj.value)


class AssetSerializer(serializers.ModelSerializer):
    """Read serializer with every derived figure the UI displays."""

    current_value = serializers.SerializerMethodField()
    nominal_return = serializers.SerializerMethodField()
    nominal_return_percent = serializers.SerializerMethodField()

    current_value_display = serializers.SerializerMethodField()
    purchase_value_display = serializers.SerializerMethodField()
    nominal_return_display = serializers.SerializerMethodField()
    nominal_return_percent_display = serializers.SerializerMethodField()
    total_cost_display = serializers.SerializerMethodField()

    asset_type_label = serializers.CharField(source="get_asset_type_display", read_only=True)
    purchase_date_display = serializers.SerializerMethodField()
    last_valued_on = serializers.SerializerMethodField()
    is_profitable = serializers.BooleanField(read_only=True)
    owner_name = serializers.SerializerMethodField()

    class Meta:
        model = Asset
        fields = (
            "id",
            "name",
            "asset_type",
            "asset_type_label",
            "current_value",
            "current_value_display",
            "purchase_value",
            "purchase_value_display",
            "nominal_return",
            "nominal_return_display",
            "nominal_return_percent",
            "nominal_return_percent_display",
            "is_profitable",
            "total_cost_display",
            "quantity",
            "unit",
            "unit_price",
            "purchase_date",
            "purchase_date_display",
            "last_valued_on",
            "description",
            "note",
            "provider",
            "account",
            "owner_name",
            "include_in_net_worth",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def _current(self, obj) -> Decimal:
        annotated = getattr(obj, "current_value_annotated", None)
        if annotated is not None:
            return quantize_money(annotated)
        return quantize_money(obj.current_value)

    def get_current_value(self, obj) -> str:
        return str(self._current(obj))

    def get_nominal_return(self, obj) -> str:
        return str(quantize_money(self._current(obj) - (obj.purchase_value or Decimal("0.00"))))

    def get_nominal_return_percent(self, obj) -> str:
        gain = self._current(obj) - (obj.purchase_value or Decimal("0.00"))
        return str(percentage(gain, obj.purchase_value or Decimal("0.00")))

    def get_current_value_display(self, obj) -> str:
        return format_money(self._current(obj))

    def get_purchase_value_display(self, obj) -> str:
        return format_money(obj.purchase_value or Decimal("0.00"))

    def get_nominal_return_display(self, obj) -> str:
        gain = self._current(obj) - (obj.purchase_value or Decimal("0.00"))
        return format_money(gain)

    def get_nominal_return_percent_display(self, obj) -> str:
        gain = self._current(obj) - (obj.purchase_value or Decimal("0.00"))
        return format_percent(percentage(gain, obj.purchase_value or Decimal("0.00")))

    def get_total_cost_display(self, obj) -> str:
        return format_money(obj.purchase_value or Decimal("0.00"))

    def get_purchase_date_display(self, obj) -> str | None:
        return format_jalali(obj.purchase_date, style="short") if obj.purchase_date else None

    def get_last_valued_on(self, obj) -> dict | None:
        valuation = obj.valuations.order_by("-valued_on", "-id").first()
        if valuation is None:
            return None
        return {
            "date": valuation.valued_on.isoformat(),
            "display": format_jalali(valuation.valued_on, style="short"),
            "value": str(quantize_money(valuation.value)),
        }

    def get_owner_name(self, obj) -> str:
        return obj.account.name if obj.account_id else (obj.provider or "—")


class AssetWriteSerializer(serializers.ModelSerializer):
    """Create/update an asset.

    Accepts `current_value` as a convenience on create: if supplied, an initial
    valuation is recorded automatically, so the user does not have to create the
    asset and then immediately add a valuation.
    """

    current_value = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, write_only=True, allow_null=True
    )

    class Meta:
        model = Asset
        fields = (
            "id",
            "name",
            "asset_type",
            "purchase_value",
            "purchase_date",
            "current_value",
            "quantity",
            "unit",
            "unit_price",
            "description",
            "note",
            "provider",
            "account",
            "include_in_net_worth",
            "is_active",
        )
        read_only_fields = ("id",)

    def validate_name(self, value):
        cleaned = (value or "").strip()
        if not cleaned:
            raise serializers.ValidationError("نام دارایی را وارد کنید.")
        return cleaned

    def validate_purchase_value(self, value):
        amount = quantize_money(to_decimal(value))
        if amount < 0:
            raise serializers.ValidationError("ارزش خرید نمی‌تواند منفی باشد.")
        return amount

    def validate_current_value(self, value):
        if value is None:
            return None
        amount = quantize_money(to_decimal(value))
        if amount < 0:
            raise serializers.ValidationError("ارزش فعلی نمی‌تواند منفی باشد.")
        return amount

    def validate_quantity(self, value):
        if value is None:
            return value
        if value < 0:
            raise serializers.ValidationError("مقدار نمی‌تواند منفی باشد.")
        return value

    def validate_unit_price(self, value):
        if value is None:
            return value
        amount = quantize_money(to_decimal(value))
        if amount < 0:
            raise serializers.ValidationError("قیمت واحد نمی‌تواند منفی باشد.")
        return amount

    def validate_account(self, value):
        if value is None:
            return value
        request = self.context.get("request")
        if request and value.user_id != request.user.id:
            raise serializers.ValidationError("حساب انتخاب‌شده معتبر نیست.")
        return value

    def validate(self, attrs):
        request = self.context["request"]
        instance = self.instance

        name = attrs.get("name", getattr(instance, "name", ""))

        duplicates = Asset.objects.filter(user=request.user, name=name)
        if instance is not None:
            duplicates = duplicates.exclude(pk=instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError(
                {"name": "دارایی‌ای با این نام قبلاً ثبت شده است."}
            )

        quantity = attrs.get("quantity", getattr(instance, "quantity", None))
        unit_price = attrs.get("unit_price", getattr(instance, "unit_price", None))

        # If both quantity and unit price are given but no purchase value, it is
        # almost certainly what the user meant — derive it rather than asking
        # them to compute it themselves.
        purchase_value = attrs.get("purchase_value", getattr(instance, "purchase_value", None))
        if purchase_value in (None, Decimal("0.00")) and quantity and unit_price:
            attrs["purchase_value"] = quantize_money(quantity * unit_price)

        return attrs

    def create(self, validated_data):
        current_value = validated_data.pop("current_value", None)
        asset = Asset.objects.create(**validated_data)

        # Record an opening valuation so the asset has a value from day one.
        initial = current_value if current_value is not None else asset.purchase_value
        if initial and initial > 0:
            AssetValuation.objects.create(
                asset=asset,
                value=initial,
                valued_on=asset.purchase_date or dt.date.today(),
                note="ارزش اولیه",
            )
        return asset

    def update(self, instance, validated_data):
        current_value = validated_data.pop("current_value", None)

        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()

        # A changed current value becomes a new valuation rather than
        # overwriting history.
        if current_value is not None:
            AssetValuation.objects.update_or_create(
                asset=instance,
                valued_on=dt.date.today(),
                defaults={"value": current_value, "note": "بروزرسانی ارزش"},
            )
        return instance


class AssetValuationWriteSerializer(serializers.ModelSerializer):
    """Record a new valuation for an asset."""

    class Meta:
        model = AssetValuation
        fields = ("id", "value", "valued_on", "note")
        read_only_fields = ("id",)

    def validate_value(self, value):
        amount = quantize_money(to_decimal(value))
        if amount < 0:
            raise serializers.ValidationError("ارزش نمی‌تواند منفی باشد.")
        return amount

    def validate_valued_on(self, value):
        """Allow a future valuation, within a bounded horizon.

        Valuations are usually a statement of what something is worth today,
        but forward-dating is legitimate for a known future event: a deposit
        maturing, a property revaluation scheduled for next quarter. The bound
        mirrors the transaction rule and exists to catch a mistyped year rather
        than to forbid planning.
        """
        from apps.transactions.serializers import FUTURE_HORIZON_DAYS

        if value > dt.date.today() + dt.timedelta(days=FUTURE_HORIZON_DAYS):
            raise serializers.ValidationError(
                f"تاریخ ارزش‌گذاری نمی‌تواند بیش از {FUTURE_HORIZON_DAYS} روز در آینده باشد."
            )
        return value

    def validate(self, attrs):
        asset = self.context.get("asset")
        if asset is None:
            raise serializers.ValidationError("دارایی مشخص نشده است.")

        valued_on = attrs.get("valued_on", dt.date.today())

        # One valuation per day per asset (mirrors the DB constraint, but with a
        # Persian message).
        existing = AssetValuation.objects.filter(asset=asset, valued_on=valued_on)
        if self.instance is not None:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError(
                {"valued_on": "برای این تاریخ قبلاً ارزش ثبت شده است."}
            )

        return attrs
