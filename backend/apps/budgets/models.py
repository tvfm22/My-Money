"""Budgeting models.

Structure
---------
A ``Budget`` is one monthly plan: "شهریور ۱۴۰۵". It holds the overall envelope
(planned income, savings target, and the derived flexible budget) and owns a set
of ``BudgetItem`` rows — one per category being budgeted.

    Budget (1405/06)
      ├── BudgetItem  خوراک           8,000,000
      ├── BudgetItem  رستوران و کافه   3,000,000
      ├── BudgetItem  حمل‌ونقل         2,000,000
      └── BudgetItem  سرگرمی          1,500,000

Why (year, month) instead of a date range
----------------------------------------
Budgets are inherently monthly in personal finance. Storing the Jalali year and
month directly means "show me شهریور" is an exact key lookup, and month
boundaries can never be mis-set by a caller. The Gregorian range is derived on
demand via `apps.core.jalali.jalali_month_bounds`.

Spending is never stored
------------------------
`spent` on a BudgetItem is computed from actual transactions every time it is
read. Storing it would require invalidating the cache on every transaction
write, and any miss would show the user a wrong number about their own money.
The queries are indexed for exactly this access pattern.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class BudgetQuerySet(models.QuerySet):
    def for_user(self, user):
        return self.filter(user=user)

    def for_month(self, year: int, month: int):
        return self.filter(year=year, month=month)

    def with_items(self):
        return self.prefetch_related(
            models.Prefetch(
                "items",
                queryset=BudgetItem.objects.select_related("category", "category__parent"),
            )
        )


class Budget(models.Model):
    """A monthly budget envelope for one user."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="budgets",
        verbose_name="کاربر",
    )

    # Jalali year/month. This is the natural key users think in.
    year = models.PositiveSmallIntegerField("سال", db_index=True)
    month = models.PositiveSmallIntegerField("ماه", db_index=True)

    # --- Monthly plan (section 12 of the spec) ---------------------------
    expected_income = models.DecimalField(
        "درآمد پیش‌بینی‌شده",
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    savings_target = models.DecimalField(
        "پس‌انداز هدف",
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    investment_target = models.DecimalField(
        "سرمایه‌گذاری هدف",
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    debt_payment_target = models.DecimalField(
        "بازپرداخت بدهی هدف",
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    note = models.TextField("یادداشت", blank=True)

    is_active = models.BooleanField("فعال", default=True)

    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین بروزرسانی", auto_now=True)

    objects = BudgetQuerySet.as_manager()

    class Meta:
        verbose_name = "بودجه"
        verbose_name_plural = "بودجه‌ها"
        # One budget per user per month is the correct constraint: two
        # competing budgets for the same month would make "am I within budget?"
        # unanswerable.
        constraints = [
            models.UniqueConstraint(
                fields=["user", "year", "month"],
                name="unique_budget_per_user_month",
            ),
            models.CheckConstraint(
                condition=models.Q(month__gte=1) & models.Q(month__lte=12),
                name="budget_month_in_range",
            ),
        ]
        ordering = ("-year", "-month")
        indexes = [
            models.Index(fields=["user", "year", "month"], name="budget_user_ym_idx"),
        ]

    def __str__(self) -> str:
        return f"بودجه {self.month_name} {self.year}"

    # ------------------------------------------------------------------
    # Basic accessors
    # ------------------------------------------------------------------

    @property
    def month_name(self) -> str:
        from apps.core.jalali import PERSIAN_MONTHS

        if 1 <= self.month <= 12:
            return PERSIAN_MONTHS[self.month - 1]
        return ""

    @property
    def label(self) -> str:
        """'شهریور ۱۴۰۵' — the string used across the UI."""
        from apps.core.jalali import month_label

        return month_label(self.year, self.month)

    @property
    def date_range(self):
        """Inclusive Gregorian (first, last) dates for this Jalali month."""
        from apps.core.jalali import jalali_month_bounds

        return jalali_month_bounds(self.year, self.month)

    # ------------------------------------------------------------------
    # Allocated totals
    # ------------------------------------------------------------------

    @property
    def allocated_total(self) -> Decimal:
        """Sum of all category allocations in this budget."""
        result = self.items.aggregate(total=models.Sum("amount"))["total"]
        return result or Decimal("0.00")

    @property
    def committed_total(self) -> Decimal:
        """Everything the plan commits: categories + savings + investment + debt.

        This is what gets compared against `expected_income` to see whether the
        month's plan is internally consistent.
        """
        return (
            self.allocated_total
            + (self.savings_target or Decimal("0.00"))
            + (self.investment_target or Decimal("0.00"))
            + (self.debt_payment_target or Decimal("0.00"))
        )

    @property
    def flexible_budget(self) -> Decimal:
        """Unallocated income: the "بودجه آزاد" figure from the spec.

        Can legitimately go negative, which is meaningful — it means the plan
        allocates more than the expected income, and the user should be told.
        """
        return (self.expected_income or Decimal("0.00")) - self.committed_total

    @property
    def is_oversubscribed(self) -> bool:
        """True when the plan commits more than the expected income."""
        return self.flexible_budget < 0


class BudgetItem(models.Model):
    """A single category allocation inside a monthly budget."""

    budget = models.ForeignKey(
        Budget,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="بودجه",
    )

    category = models.ForeignKey(
        "categories.Category",
        on_delete=models.CASCADE,
        related_name="budget_items",
        verbose_name="دسته‌بندی",
    )

    amount = models.DecimalField(
        "مبلغ بودجه",
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"), "مبلغ بودجه نمی‌تواند منفی باشد.")],
    )

    # Marks a line the user considers non-negotiable (rent, utilities).
    # Drives the essential/flexible split in the monthly plan breakdown.
    is_essential = models.BooleanField("هزینه ضروری", default=False)

    note = models.CharField("یادداشت", max_length=200, blank=True)

    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین بروزرسانی", auto_now=True)

    class Meta:
        verbose_name = "ردیف بودجه"
        verbose_name_plural = "ردیف‌های بودجه"
        ordering = ("-amount",)
        constraints = [
            # A category cannot appear twice in the same month's budget; the
            # second row would silently double-count spending.
            models.UniqueConstraint(
                fields=["budget", "category"],
                name="unique_budget_item_per_category",
            ),
        ]
        indexes = [
            models.Index(fields=["budget", "category"], name="bitem_budget_cat_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.category.name}: {self.amount}"

    @property
    def user_id(self) -> int:
        """Expose the owning user, so `IsOwner` works uniformly.

        BudgetItem has no `user` column of its own — ownership is inherited from
        the parent Budget. This property means generic permission checks and
        queryset scoping can treat it like any other user-owned object.
        """
        return self.budget.user_id

    @property
    def category_name(self) -> str:
        return self.category.full_path if self.category_id else ""
