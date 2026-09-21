"""Assets, valuations, and net worth.

Two-level model
---------------
An ``Asset`` is the thing the user owns ("صندوق طلا", "آپارتمان"). An
``AssetValuation`` is a dated snapshot of what it was worth. Current value is
the most recent valuation.

Why valuations rather than a mutable `current_value` column
----------------------------------------------------------
Overwriting a single value column destroys history, and history is exactly what
makes a net-worth-over-time chart possible. Keeping every valuation as a row
means:

*   The current value is `valuations.latest('valued_on').value`.
*   The net worth chart is a query over valuation history, not a separate
    snapshot table that has to be kept in sync.
*   A user correcting a typo adds a new valuation rather than losing the old one.

`purchase_value` and `purchase_date` are stored separately, so nominal return
(`current - purchase`) is always computable.

No live market data
-------------------
The spec explicitly defers automatic price retrieval. Values here are whatever
the user last entered; nothing is fetched, and nothing pretends to be live.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Prefetch


class AssetType(models.TextChoices):
    """Asset kinds, following the product spec's examples."""

    BANK_ACCOUNT = "bank_account", "حساب بانکی"
    CASH = "cash", "وجه نقد"
    GOLD_FUND = "gold_fund", "صندوق طلا"
    GOLD = "gold", "طلا"
    STOCKS = "stocks", "سهام"
    CURRENCY = "currency", "ارز"
    REAL_ESTATE = "real_estate", "ملک"
    VEHICLE = "vehicle", "خودرو"
    DEPOSIT = "deposit", "سپرده"
    CRYPTO = "crypto", "رمزارز"
    OTHER = "other", "سایر دارایی‌ها"


class AssetQuerySet(models.QuerySet):
    def for_user(self, user):
        return self.filter(user=user)

    def active(self):
        return self.filter(is_active=True)

    def with_valuations(self):
        return self.prefetch_related(
            Prefetch("valuations", queryset=AssetValuation.objects.order_by("-valued_on"))
        )


class Asset(models.Model):
    """Something the user owns."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assets",
        verbose_name="کاربر",
    )

    name = models.CharField("نام دارایی", max_length=120)

    asset_type = models.CharField(
        "نوع دارایی",
        max_length=20,
        choices=AssetType.choices,
        default=AssetType.OTHER,
        db_index=True,
    )

    # --- Purchase side ---------------------------------------------------
    purchase_value = models.DecimalField(
        "ارزش خرید",
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"), "ارزش خرید نمی‌تواند منفی باشد.")],
    )
    purchase_date = models.DateField("تاریخ خرید", null=True, blank=True)

    # --- Quantity (optional: meaningful for funds, gold, stocks) ---------
    quantity = models.DecimalField(
        "مقدار",
        max_digits=20,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="برای دارایی‌هایی مانند صندوق، طلا یا سهام",
    )
    unit = models.CharField(
        "واحد", max_length=30, blank=True, help_text="مثلاً «واحد»، «گرم»، «سهم»"
    )
    unit_price = models.DecimalField(
        "قیمت واحد",
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="در صورت ثبت مقدار، قیمت هر واحد",
    )

    description = models.CharField("توضیح", max_length=200, blank=True)
    note = models.TextField("یادداشت", blank=True)

    # Optional provider, e.g. "بانک ملت" or "کارگزاری مفید".
    provider = models.CharField("مؤسسه / ارائه‌دهنده", max_length=80, blank=True)

    # Optional link to a wallet account.
    account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assets",
        verbose_name="حساب مرتبط",
    )

    include_in_net_worth = models.BooleanField("محاسبه در ارزش کل", default=True)
    is_active = models.BooleanField("فعال", default=True)

    created_at = models.DateTimeField("تاریخ ثبت", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین بروزرسانی", auto_now=True)

    objects = AssetQuerySet.as_manager()

    class Meta:
        verbose_name = "دارایی"
        verbose_name_plural = "دارایی‌ها"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["user", "asset_type"], name="asset_user_type_idx"),
            models.Index(fields=["user", "is_active"], name="asset_user_active_idx"),
        ]

    def __str__(self) -> str:
        return self.name

    # ------------------------------------------------------------------
    # Value resolution
    # ------------------------------------------------------------------
    #
    # These properties issue a query each. Views that list assets annotate the
    # latest value instead — see `apps.assets.services.annotate_current_value`.

    @property
    def latest_valuation(self) -> "AssetValuation | None":
        return self.valuations.order_by("-valued_on", "-id").first()

    @property
    def current_value(self) -> Decimal:
        """Most recent recorded value, falling back to what was paid."""
        valuation = self.latest_valuation
        if valuation is not None:
            return valuation.value
        return self.purchase_value or Decimal("0.00")

    @property
    def nominal_return(self) -> Decimal:
        """Absolute gain or loss against the purchase value."""
        return self.current_value - (self.purchase_value or Decimal("0.00"))

    @property
    def nominal_return_percent(self) -> Decimal:
        from apps.core.money import percentage

        return percentage(self.nominal_return, self.purchase_value or Decimal("0.00"))

    @property
    def is_profitable(self) -> bool:
        return self.nominal_return > 0

    @property
    def has_history(self) -> bool:
        return self.valuations.count() > 1


class AssetValuation(models.Model):
    """A dated snapshot of what an asset was worth."""

    asset = models.ForeignKey(
        Asset,
        on_delete=models.CASCADE,
        related_name="valuations",
        verbose_name="دارایی",
    )

    value = models.DecimalField(
        "ارزش",
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"), "ارزش نمی‌تواند منفی باشد.")],
    )

    valued_on = models.DateField("تاریخ ارزش‌گذاری", db_index=True)

    note = models.CharField("یادداشت", max_length=200, blank=True)

    created_at = models.DateTimeField("تاریخ ثبت", auto_now_add=True)

    class Meta:
        verbose_name = "ارزش‌گذاری"
        verbose_name_plural = "ارزش‌گذاری‌ها"
        ordering = ("-valued_on", "-id")
        constraints = [
            # One value per asset per day. Two valuations on the same date would
            # make "the current value" ambiguous.
            models.UniqueConstraint(
                fields=["asset", "valued_on"],
                name="unique_valuation_per_asset_per_day",
            ),
        ]
        indexes = [
            models.Index(fields=["asset", "valued_on"], name="valuation_asset_date_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.asset.name}: {self.value} @ {self.valued_on}"

    @property
    def user_id(self) -> int:
        """Ownership inherited from the parent asset."""
        return self.asset.user_id
