"""Tags and transactions.

Transaction model notes
-----------------------
*   `amount` is always a positive Decimal. Direction is carried by
    `transaction_type`. This avoids the classic bug where a negative expense
    and a positive income cancel out in an aggregate and hide a problem, and it
    makes every sum in the app a plain `Sum('amount')` filtered by type.
*   `transaction_type` is denormalized from the category's `kind` on save.
    Storing it on the row means reports never need to join `categories` to know
    which direction a transaction went.
*   `occurred_on` is a `DateField`, not a `DateTimeField`. A personal finance
    transaction happened on a day; the time of day is not meaningful and would
    only introduce timezone ambiguity into month boundaries.
*   `occurred_at` (UTC timestamp of creation) and `occurred_on` are distinct:
    the former is an audit trail, the latter is the user-facing date.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone


class TransactionType(models.TextChoices):
    EXPENSE = "expense", "هزینه"
    INCOME = "income", "درآمد"


class SpendingType(models.TextChoices):
    """How the user classified an expense when they recorded it.

    Deliberately a *judgement*, not a calculation. Only the person who spent the
    money knows whether a purchase was something they had to make, something
    they chose to make, or money they regret. The app reports the split; it
    never infers it from the category — «مسکن» can be wasted money if it is an
    inflated rent, and «سرگرمی» can be essential if it is the thing keeping you
    sane.

    Income carries no classification at all, which is why the field is blank
    rather than defaulted for income rows.
    """

    ESSENTIAL = "essential", "ضروری"
    FLEXIBLE = "flexible", "انعطاف‌پذیر"
    WASTED = "wasted", "غیرضروری"


class Tag(models.Model):
    """A user-scoped label that can be attached to any transaction."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tags",
        verbose_name="کاربر",
    )

    name = models.CharField("نام برچسب", max_length=40)
    color = models.CharField("رنگ", max_length=20, default="slate")

    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)

    class Meta:
        verbose_name = "برچسب"
        verbose_name_plural = "برچسب‌ها"
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=["user", "name"], name="unique_tag_name_per_user"
            ),
        ]
        indexes = [models.Index(fields=["user"], name="tag_user_idx")]

    def __str__(self) -> str:
        return self.name


class TransactionQuerySet(models.QuerySet):
    def for_user(self, user):
        return self.filter(user=user)

    def expenses(self):
        return self.filter(transaction_type=TransactionType.EXPENSE)

    def incomes(self):
        return self.filter(transaction_type=TransactionType.INCOME)

    def between(self, start, end):
        """Inclusive date range."""
        return self.filter(occurred_on__gte=start, occurred_on__lte=end)

    def with_relations(self):
        """Everything the list serializer reads, in one query."""
        return self.select_related("category", "category__parent", "account").prefetch_related(
            "tags"
        )

    def recent_first(self):
        return self.order_by("-occurred_on", "-created_at", "-id")


class Transaction(models.Model):
    """A single recorded income or expense."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="transactions",
        verbose_name="کاربر",
    )

    transaction_type = models.CharField(
        "نوع",
        max_length=10,
        choices=TransactionType.choices,
        db_index=True,
    )

    # How the user classified this expense: ضروری / انعطاف‌پذیر / غیرضروری.
    # Blank on income, which has no such notion. `save()` enforces both sides of
    # that rule so every write path agrees.
    spending_type = models.CharField(
        "نوع هزینه",
        max_length=10,
        choices=SpendingType.choices,
        blank=True,
        default="",
    )

    # Positive magnitude only — direction lives in `transaction_type`.
    amount = models.DecimalField(
        "مبلغ",
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"), "مبلغ باید بیشتر از صفر باشد.")],
    )

    category = models.ForeignKey(
        "categories.Category",
        on_delete=models.PROTECT,
        related_name="transactions",
        verbose_name="دسته‌بندی",
    )

    account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
        verbose_name="حساب",
    )

    # The user-facing date. See the module docstring for why this is a DateField.
    occurred_on = models.DateField("تاریخ", default=timezone.localdate, db_index=True)

    description = models.CharField("توضیح", max_length=200, blank=True)
    note = models.TextField("یادداشت", blank=True)

    tags = models.ManyToManyField(
        "transactions.Tag",
        blank=True,
        related_name="transactions",
        verbose_name="برچسب‌ها",
    )

    # Audit trail (UTC), distinct from the user-facing date.
    created_at = models.DateTimeField("زمان ثبت", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین ویرایش", auto_now=True)

    objects = TransactionQuerySet.as_manager()

    class Meta:
        verbose_name = "تراکنش"
        verbose_name_plural = "تراکنش‌ها"
        # Chronological ordering is what every list and report expects.
        ordering = ("-occurred_on", "-created_at", "-id")
        indexes = [
            # The single most-used access path: a user's transactions in a
            # date range, split by direction. Reports and budget calculations
            # both hammer this.
            models.Index(
                fields=["user", "occurred_on"], name="tx_user_date_idx"
            ),
            models.Index(
                fields=["user", "transaction_type", "occurred_on"],
                name="tx_user_type_date_idx",
            ),
            # Budget consumption: sum expenses per category in a month.
            models.Index(
                fields=["user", "category", "occurred_on"],
                name="tx_user_cat_date_idx",
            ),
            # The essential / flexible / wasted split: sum expenses by
            # classification over a date range. Reports and the dashboard both
            # run this on every load.
            models.Index(
                fields=["user", "spending_type", "occurred_on"],
                name="tx_user_spend_date_idx",
            ),
            models.Index(fields=["user", "account"], name="tx_user_account_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="transaction_amount_positive",
            ),
        ]

    def __str__(self) -> str:
        sign = "-" if self.transaction_type == TransactionType.EXPENSE else "+"
        return f"{sign}{self.amount} {self.description}".strip()

    def save(self, *args, **kwargs):
        """Keep the classification consistent with the direction.

        Two invariants live here rather than at each call site, because they
        have to hold for every write path — the API, the admin, the seed
        command and the shell:

        * an expense always carries a classification, defaulting to
          ``flexible`` when the caller did not supply one;
        * income never carries one.

        Note what this deliberately does **not** do: it never resets a
        classification that is already set. A PATCH that omits the field leaves
        the stored value alone. Silently defaulting an omitted value back to
        ``flexible`` is precisely the bug that wiped the budget-level
        ``is_essential`` flag on every re-plan, and it is not repeated here.
        """
        if self.transaction_type == TransactionType.INCOME:
            self.spending_type = ""
        elif not self.spending_type:
            self.spending_type = SpendingType.FLEXIBLE

        # A caller that names its `update_fields` must not accidentally skip the
        # normalisation above — that would leave income rows classified.
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = set(update_fields) | {"spending_type"}

        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # Derived helpers
    # ------------------------------------------------------------------

    @property
    def spending_type_label(self) -> str:
        """The Persian label, or an empty string on an income row."""
        if not self.spending_type:
            return ""
        return self.get_spending_type_display()

    @property
    def is_expense(self) -> bool:
        return self.transaction_type == TransactionType.EXPENSE

    @property
    def is_income(self) -> bool:
        return self.transaction_type == TransactionType.INCOME

    @property
    def signed_amount(self) -> Decimal:
        """Amount with direction applied, for net calculations."""
        return -self.amount if self.is_expense else self.amount

    @property
    def display_title(self) -> str:
        """Best available label: description, else category, else a generic term."""
        if self.description:
            return self.description
        if self.category_id:
            return self.category.name
        return "تراکنش بدون توضیح"


# Convenience aliases so callers can write `Transaction.objects.expenses()`
# without importing the enum, matching the queryset helper names.
def expense_total(queryset) -> Decimal:
    """Sum a transaction queryset, returning an exact Decimal zero when empty."""
    return queryset.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
