"""Debts and receivables.

One model, two directions
------------------------
"I owe Ali 10,000,000" and "Sara owes me 2,000,000" are the same shape of data
seen from opposite sides. Modelling them as one `Debt` with a `direction` field
means one set of calculations, one set of views, and one place for the
remaining-balance logic to be correct — rather than two half-features that drift
apart.

    direction = "payable"    → بدهی من (money I owe)
    direction = "receivable" → طلب من  (money owed to me)

Payments
--------
Partial payments are first-class: `DebtPayment` rows are recorded against a
debt, and the outstanding balance is derived as ``principal - sum(payments)``.
Payments are never edited into the debt's stored amount, so the history of what
was actually paid — and when — is preserved.

Status is derived, never stored
-------------------------------
`status` is computed from the balance and the due date:
    settled      — balance is zero
    overdue      — past the due date with a balance outstanding
    partial      — some payment made, balance remains
    active       — nothing paid yet, not yet due
This means a debt can never be stuck showing "فعال" after its due date passed,
which a stored status column would eventually do.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, Sum


class DebtDirection(models.TextChoices):
    PAYABLE = "payable", "بدهی من"
    RECEIVABLE = "receivable", "طلب من"


class DebtStatus(models.TextChoices):
    ACTIVE = "active", "فعال"
    PARTIAL = "partial", "بخشی پرداخت شده"
    SETTLED = "settled", "تسویه شده"
    OVERDUE = "overdue", "سررسید گذشته"


class DebtQuerySet(models.QuerySet):
    def for_user(self, user):
        return self.filter(user=user)

    def payable(self):
        return self.filter(direction=DebtDirection.PAYABLE)

    def receivable(self):
        return self.filter(direction=DebtDirection.RECEIVABLE)

    def unsettled(self):
        return self.filter(settled_at__isnull=True)

    def with_payments(self):
        return self.prefetch_related("payments")


class Debt(models.Model):
    """A single obligation in either direction."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="debts",
        verbose_name="کاربر",
    )

    direction = models.CharField(
        "جهت",
        max_length=12,
        choices=DebtDirection.choices,
        default=DebtDirection.PAYABLE,
        db_index=True,
    )

    # Free text rather than a contact FK: debts are often with a shop, a
    # landlord or an employer, and requiring a contact record first would add
    # friction to the most common case.
    counterparty = models.CharField("طرف حساب", max_length=120)

    principal = models.DecimalField(
        "مبلغ کل",
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"), "مبلغ باید بیشتر از صفر باشد.")],
    )

    # The original Jalali date the debt was taken on.
    issued_on = models.DateField("تاریخ ایجاد", null=True, blank=True)

    due_on = models.DateField(
        "سررسید",
        null=True,
        blank=True,
        db_index=True,
        help_text="تاریخ سررسید (میلادی ذخیره می‌شود، در رابط کاربری شمسی نمایش داده می‌شود)",
    )

    description = models.CharField("توضیح", max_length=200, blank=True)
    note = models.TextField("یادداشت", blank=True)

    # Optional link to the account the money moved through.
    account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="debts",
        verbose_name="حساب مرتبط",
    )

    # Set when the balance first reaches zero, so "settled" is a fact with a
    # timestamp rather than a guess from the current balance.
    settled_at = models.DateTimeField("زمان تسویه", null=True, blank=True)

    created_at = models.DateTimeField("تاریخ ثبت", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین بروزرسانی", auto_now=True)

    objects = DebtQuerySet.as_manager()

    class Meta:
        verbose_name = "بدهی / طلب"
        verbose_name_plural = "بدهی‌ها و طلب‌ها"
        ordering = ("-created_at",)
        indexes = [
            models.Index(
                fields=["user", "direction", "settled_at"], name="debt_user_dir_settled_idx"
            ),
            models.Index(fields=["user", "due_on"], name="debt_user_due_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(principal__gt=0), name="debt_principal_positive"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_direction_display()} — {self.counterparty}"

    # ------------------------------------------------------------------
    # Derived amounts
    # ------------------------------------------------------------------

    @property
    def paid_amount(self) -> Decimal:
        result = self.payments.aggregate(total=Sum("amount"))["total"]
        return result or Decimal("0.00")

    @property
    def remaining_amount(self) -> Decimal:
        """Outstanding balance. Never negative, even if overpaid."""
        remaining = self.principal - self.paid_amount
        return remaining if remaining > 0 else Decimal("0.00")

    @property
    def paid_percent(self) -> Decimal:
        from apps.core.money import percentage

        return percentage(self.paid_amount, self.principal)

    @property
    def is_settled(self) -> bool:
        return self.settled_at is not None or self.remaining_amount <= 0

    @property
    def is_overdue(self) -> bool:
        """Past the due date with a balance still outstanding."""
        import datetime as dt

        if self.due_on is None or self.is_settled:
            return False
        return self.due_on < dt.date.today()

    @property
    def days_until_due(self) -> int | None:
        """Negative when overdue. None when there is no due date."""
        import datetime as dt

        if self.due_on is None:
            return None
        return (self.due_on - dt.date.today()).days

    @property
    def status(self) -> str:
        """Derived status. See the module docstring for why this is not stored."""
        if self.is_settled:
            return DebtStatus.SETTLED
        if self.is_overdue:
            return DebtStatus.OVERDUE
        if self.paid_amount > 0:
            return DebtStatus.PARTIAL
        return DebtStatus.ACTIVE

    @property
    def status_label(self) -> str:
        return dict(DebtStatus.choices).get(self.status, "")

    @property
    def direction_label(self) -> str:
        return self.get_direction_display()

    @property
    def is_payable(self) -> bool:
        return self.direction == DebtDirection.PAYABLE


class DebtPayment(models.Model):
    """A single payment made against (or received for) a debt."""

    debt = models.ForeignKey(
        Debt,
        on_delete=models.CASCADE,
        related_name="payments",
        verbose_name="بدهی",
    )

    amount = models.DecimalField(
        "مبلغ پرداخت",
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"), "مبلغ پرداخت باید بیشتر از صفر باشد.")],
    )

    paid_on = models.DateField("تاریخ پرداخت", db_index=True)

    note = models.CharField("یادداشت", max_length=200, blank=True)

    # The account the payment moved through, if recorded.
    account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="debt_payments",
        verbose_name="حساب",
    )

    created_at = models.DateTimeField("تاریخ ثبت", auto_now_add=True)

    class Meta:
        verbose_name = "پرداخت بدهی"
        verbose_name_plural = "پرداخت‌های بدهی"
        ordering = ("-paid_on", "-created_at")
        indexes = [
            models.Index(fields=["debt", "paid_on"], name="debtpay_debt_date_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.amount} on {self.paid_on}"

    @property
    def user_id(self) -> int:
        """Ownership inherited from the parent debt, for uniform permission checks."""
        return self.debt.user_id
