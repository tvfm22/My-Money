"""Financial accounts (wallets, bank accounts, cards, investment accounts).

Balances are *derived*, never stored as a mutable column.

Rationale: a stored `balance` field has to be updated on every transaction
create/update/delete, every debt settlement, and every asset change. Each of
those is a place where the number silently drifts out of sync with the
transactions that justify it. Instead, `opening_balance` is stored and the
current balance is computed as::

    opening_balance + income - expense  (for transactions on this account)

which is always exactly consistent with the recorded history.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class AccountType(models.TextChoices):
    """Account kinds, from the product spec's examples."""

    BANK = "bank", "حساب بانکی"
    CASH = "cash", "کیف پول نقدی"
    CARD = "card", "کارت بانکی"
    INVESTMENT = "investment", "حساب سرمایه‌گذاری"
    SAVINGS = "savings", "حساب پس‌انداز"
    CREDIT = "credit", "کارت اعتباری"
    OTHER = "other", "سایر"


class AccountQuerySet(models.QuerySet):
    def for_user(self, user):
        return self.filter(user=user)

    def active(self):
        return self.filter(is_active=True)

    def ordered(self):
        return self.order_by("sort_order", "name")


class Account(models.Model):
    """A place money sits: bank account, wallet, card, brokerage, ..."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="accounts",
        verbose_name="کاربر",
    )

    name = models.CharField("نام حساب", max_length=80)

    account_type = models.CharField(
        "نوع حساب",
        max_length=20,
        choices=AccountType.choices,
        default=AccountType.BANK,
        db_index=True,
    )

    # Where the account stands before any recorded transaction. This is what
    # makes the derived balance match the user's real bank balance on day one.
    opening_balance = models.DecimalField(
        "موجودی اولیه",
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    # Optional presentation metadata.
    color = models.CharField("رنگ", max_length=20, default="slate")
    icon = models.CharField("آیکون", max_length=40, default="wallet")

    # Free-text provider, e.g. "بانک ملت".
    institution = models.CharField("بانک / مؤسسه", max_length=80, blank=True)

    # Accounts can be individually excluded from net-worth style totals
    # (e.g. a shared household account the user does not fully own).
    include_in_total = models.BooleanField("محاسبه در مجموع", default=True)

    is_active = models.BooleanField("فعال", default=True)
    sort_order = models.PositiveSmallIntegerField("ترتیب نمایش", default=100)

    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین بروزرسانی", auto_now=True)

    objects = AccountQuerySet.as_manager()

    class Meta:
        verbose_name = "حساب"
        verbose_name_plural = "حساب‌ها"
        ordering = ("sort_order", "name")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "name"],
                name="unique_account_name_per_user",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "is_active"], name="acct_user_active_idx"),
        ]

    def __str__(self) -> str:
        return self.name

    # ----------------------------------------------------------------------
    # Derived figures
    #
    # These read from the related transactions. Callers that list many accounts
    # should annotate instead, to avoid N+1 queries — see `with_totals()`.
    # ----------------------------------------------------------------------

    @property
    def income_total(self) -> Decimal:
        result = self._own_transactions().filter(
            transaction_type="income"
        ).aggregate(total=models.Sum("amount"))["total"]
        return result or Decimal("0.00")

    @property
    def expense_total(self) -> Decimal:
        result = self._own_transactions().filter(
            transaction_type="expense"
        ).aggregate(total=models.Sum("amount"))["total"]
        return result or Decimal("0.00")

    def _own_transactions(self):
        """Transactions on this account that belong to the account's owner.

        Scoping by ``user`` as well as ``account`` is redundant given the FK,
        but it is deliberate belt-and-braces: every financial aggregate in this
        codebase is scoped to the owner, so that a single bad row (a fixture, a
        migration, a future shared/child account feature) cannot leak one
        user's money into another user's balance.
        """
        return self.transactions.filter(user_id=self.user_id)

    @property
    def current_balance(self) -> Decimal:
        """Opening balance plus all income minus all expense on this account."""
        return (self.opening_balance or Decimal("0.00")) + self.income_total - self.expense_total
