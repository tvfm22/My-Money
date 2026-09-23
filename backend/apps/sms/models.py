"""SMS import: batches, reviewed items, and reminder state.

Why a staging table instead of writing transactions directly
-----------------------------------------------------------
A parsed SMS is a *claim* about money, not money. Its amount may have been read
from the wrong figure, its unit may have been assumed, its date may be missing
and its category is never stated at all. Writing straight into `transactions`
would put all of that into the ledger and leave the user to find and repair it —
and the ledger is what every balance, budget and report is derived from.

So an import is two steps:

1.  **Read** — messages are parsed into :class:`SmsImportItem` rows. The raw text
    is stored verbatim, so the review screen can show what the bank actually
    sent and a parser fix can be replayed later.
2.  **Commit** — the user classifies the rows they trust, and only then are
    `Transaction` rows created. Each created transaction is linked back
    (``SmsImportItem.transaction``), which is what makes an import explainable
    after the fact.

Balances are *not* written to a column
--------------------------------------
`Account` derives its balance from `opening_balance` plus its transactions (see
`apps.accounts.models`), deliberately, because a stored balance drifts. The
balance printed in an SMS is therefore used for **reconciliation**: it implies
what the opening balance must have been for the ledger to agree with the bank
(see `services.balance_reconciliation`). Nothing is written unless the user
explicitly asks for the adjustment.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.transactions.models import TransactionType


class BatchStatus(models.TextChoices):
    DRAFT = "draft", "در حال بررسی"
    COMMITTED = "committed", "ثبت‌شده"


class SmsImportBatchQuerySet(models.QuerySet):
    def for_user(self, user):
        return self.filter(user=user)

    def for_period(self, year: int, month: int):
        return self.filter(period_year=year, period_month=month)

    def with_items(self):
        """Everything the review screen reads, in one pass."""
        return self.prefetch_related("items__category", "items__account")


class SmsImportItemQuerySet(models.QuerySet):
    def for_user(self, user):
        return self.filter(user=user)

    def pending(self):
        return self.filter(status=ItemStatus.PENDING)

    def transactions(self):
        return self.filter(is_transaction=True)

    def with_relations(self):
        return self.select_related("category", "category__parent", "account", "batch")



class ItemStatus(models.TextChoices):
    PENDING = "pending", "در انتظار بررسی"
    IMPORTED = "imported", "ثبت‌شده"
    SKIPPED = "skipped", "رد شده"
    DUPLICATE = "duplicate", "تکراری"


class SmsImportBatch(models.Model):
    """One reading session: the messages pulled in for a Jalali month.

    The period is stored as Jalali year/month because that is how the user
    thinks and how the import is triggered ("پیامک‌های ماه گذشته"). Individual
    items still carry a Gregorian ``occurred_on``, because that is what the
    ledger stores — the two are different things and conflating them is how a
    month boundary ends up off by one.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sms_batches",
        verbose_name="کاربر",
    )

    period_year = models.PositiveSmallIntegerField("سال شمسی")
    period_month = models.PositiveSmallIntegerField("ماه شمسی")

    # Where the messages came from: a pasted blob, an uploaded backup file, ...
    # Free text, shown to the user; never used for logic.
    source_label = models.CharField("منبع", max_length=120, blank=True)

    # Optional: the account these messages belong to. Used for duplicate
    # detection and for balance reconciliation.
    account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sms_batches",
        verbose_name="حساب",
    )

    status = models.CharField(
        "وضعیت", max_length=12, choices=BatchStatus.choices, default=BatchStatus.DRAFT
    )
    note = models.TextField("یادداشت", blank=True)

    created_at = models.DateTimeField("زمان ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین بروزرسانی", auto_now=True)
    committed_at = models.DateTimeField("زمان ثبت", null=True, blank=True)

    objects = SmsImportBatchQuerySet.as_manager()

    class Meta:
        verbose_name = "دسته پیامک"
        verbose_name_plural = "دسته‌های پیامک"
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(
                fields=["user", "period_year", "period_month"], name="sms_batch_period_idx"
            )
        ]

    def __str__(self) -> str:
        return f"{self.period_year}-{self.period_month:02d} ({self.items.count()} پیامک)"

    @property
    def period_label(self) -> str:
        """«شهریور ۱۴۰۵» — via the one month-label helper in `core.jalali`."""
        from apps.core.jalali import month_label

        return month_label(self.period_year, self.period_month)


class SmsImportItem(models.Model):
    """One parsed message, waiting for the user's confirmation.

    Every parsed field is nullable, including ``amount``. A message that arrived
    with an unreadable figure still belongs on the review screen with its
    warning attached — dropping it would hide a transaction, and forcing a zero
    would invent one.
    """

    batch = models.ForeignKey(
        SmsImportBatch,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="دسته",
    )
    # Denormalized for the same reason `Transaction` carries its own user: every
    # query is scoped to the owner, and an item is listed without necessarily
    # loading its batch.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sms_items",
        verbose_name="کاربر",
    )

    # --- what the message was ------------------------------------------------
    raw_text = models.TextField("متن پیامک")
    sender = models.CharField("فرستنده", max_length=80, blank=True)
    bank = models.CharField("بانک", max_length=40, blank=True, db_index=True)
    bank_label = models.CharField("نام بانک", max_length=80, blank=True)
    fingerprint = models.CharField("اثر انگشت", max_length=64, db_index=True)

    is_transaction = models.BooleanField("تراکنش است", default=True)
    noise_kind = models.CharField("نوع پیام غیرتراکنشی", max_length=20, blank=True)

    # --- what the parser read ------------------------------------------------
    direction = models.CharField(
        "جهت", max_length=10, choices=TransactionType.choices, blank=True
    )
    direction_pattern = models.CharField("الگوی تشخیص", max_length=60, blank=True)

    # In Toman, like every other money column in this project. Null when the
    # message carried no figure this parser could trust.
    amount = models.DecimalField("مبلغ", max_digits=18, decimal_places=2, null=True, blank=True)
    amount_unit = models.CharField("واحد مبلغ", max_length=10, blank=True)
    amount_unit_assumed = models.BooleanField("واحد فرض‌شده", default=False)

    balance_after = models.DecimalField(
        "موجودی پس از تراکنش", max_digits=18, decimal_places=2, null=True, blank=True
    )
    balance_label = models.CharField("برچسب موجودی", max_length=60, blank=True)

    occurred_on = models.DateField("تاریخ", null=True, blank=True, db_index=True)
    date_source = models.CharField("منبع تاریخ", max_length=12, blank=True)

    confidence = models.DecimalField(
        "اطمینان", max_digits=4, decimal_places=3, default=Decimal("0")
    )
    field_confidence = models.JSONField("اطمینان هر فیلد", default=dict, blank=True)

    card_last4 = models.CharField("چهار رقم آخر کارت", max_length=4, blank=True)
    merchant = models.CharField("پذیرنده", max_length=120, blank=True)
    warnings = models.JSONField("هشدارها", default=list, blank=True)

    # --- what the user decided ----------------------------------------------
    category = models.ForeignKey(
        "categories.Category",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sms_items",
        verbose_name="دسته‌بندی",
    )
    account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sms_items",
        verbose_name="حساب",
    )
    spending_type = models.CharField("نوع هزینه", max_length=10, blank=True, default="")
    description = models.CharField("توضیح", max_length=200, blank=True)
    note = models.TextField("یادداشت", blank=True)

    status = models.CharField(
        "وضعیت", max_length=12, choices=ItemStatus.choices, default=ItemStatus.PENDING
    )
    transaction = models.OneToOneField(
        "transactions.Transaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sms_item",
        verbose_name="تراکنش ثبت‌شده",
    )

    created_at = models.DateTimeField("زمان ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین بروزرسانی", auto_now=True)

    objects = SmsImportItemQuerySet.as_manager()

    class Meta:
        verbose_name = "قلم پیامک"
        verbose_name_plural = "اقلام پیامک"
        ordering = ("-occurred_on", "id")
        constraints = [
            # The same message cannot appear twice inside one reading session.
            # Across sessions it is allowed but flagged as a duplicate, because
            # re-importing a month must stay possible.
            models.UniqueConstraint(
                fields=["batch", "fingerprint"], name="unique_fingerprint_per_batch"
            ),
        ]
        indexes = [
            models.Index(fields=["batch", "status"], name="sms_item_batch_status_idx"),
            models.Index(fields=["user", "fingerprint"], name="sms_item_user_fp_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.bank_label or 'پیامک'} {self.amount if self.amount is not None else '—'}"

    # ------------------------------------------------------------------
    # Derived helpers
    # ------------------------------------------------------------------

    @property
    def is_ready(self) -> bool:
        """Everything a `Transaction` needs is present and chosen."""
        return bool(
            self.is_transaction
            and self.direction
            and self.amount is not None
            and self.category_id
        )

    @property
    def amount_display(self) -> str | None:
        """Formatted amount, or ``None`` — never a formatted zero."""
        if self.amount is None:
            return None
        from apps.core.jalali import format_money

        return format_money(self.amount)

    @property
    def balance_display(self) -> str | None:
        """Formatted balance, or ``None`` when the message printed none."""
        if self.balance_after is None:
            return None
        from apps.core.jalali import format_money

        return format_money(self.balance_after)


class SmsAutoImport(models.Model):
    """The user's switch for automatic message reading, and when it last ran.

    Why the switch is stored rather than kept in the browser
    --------------------------------------------------------
    A switch that lives in `localStorage` is a switch per *device*, and it would
    silently disagree with itself the moment the user opened the app somewhere
    else. Storing it on the server makes "off" mean off everywhere, and gives
    the checking routine one authoritative answer to consult.

    The last-check summary is a *snapshot for display* — how many messages the
    previous run looked at and how many were new. Nothing is derived from it;
    the counts on screen are recomputed from the ledger every time the state is
    read, so a stale snapshot can never make a number wrong.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sms_auto_import",
        verbose_name="کاربر",
    )
    is_enabled = models.BooleanField("فعال", default=False)

    last_checked_at = models.DateTimeField("آخرین بررسی", null=True, blank=True)
    last_check_summary = models.JSONField("خلاصه آخرین بررسی", default=dict, blank=True)

    created_at = models.DateTimeField("زمان ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین بروزرسانی", auto_now=True)

    class Meta:
        verbose_name = "دریافت خودکار پیامک"
        verbose_name_plural = "دریافت خودکار پیامک"

    def __str__(self) -> str:
        return f"{self.user_id} — {'فعال' if self.is_enabled else 'غیرفعال'}"


class SmsReminderDismissal(models.Model):
    """Records that the user hid the monthly reminder for one period.

    Stored per user and period rather than as a flag on a batch: the reminder is
    about a *month*, and a user may dismiss it without importing anything (they
    paid cash that month, or the messages are on another phone). Tying the state
    to a batch would mean a dismissal could only exist after an import.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sms_reminder_dismissals",
        verbose_name="کاربر",
    )
    period_year = models.PositiveSmallIntegerField("سال شمسی")
    period_month = models.PositiveSmallIntegerField("ماه شمسی")
    created_at = models.DateTimeField("زمان بستن", auto_now_add=True)

    class Meta:
        verbose_name = "بستن یادآور پیامک"
        verbose_name_plural = "بستن یادآورهای پیامک"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "period_year", "period_month"],
                name="unique_sms_reminder_dismissal",
            )
        ]

    def __str__(self) -> str:
        return f"{self.period_year}-{self.period_month:02d}"


