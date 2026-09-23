"""SMS import services: splitting, staging, classifying, committing.

The monthly flow this exists for
--------------------------------
At the start of a Jalali month the user is reminded that last month's messages
are waiting, opens the import screen, and pastes (or uploads) them. This module
turns that paste into reviewed rows:

    split_messages  ->  parse_sms (per message)  ->  SmsImportItem rows
                                                        |
                                    user picks categories + notes
                                                        |
                                  create_transactions_for_batch -> Transaction rows

Nothing here writes to the ledger except :func:`commit_batch`, which is the one
function whose name says it does.

Why the ledger is written only on commit
----------------------------------------
Everything the parser produces is a guess with a confidence attached. Committing
is the user's statement that a row is right. Keeping that boundary in a function
boundary — rather than in a flag — is what makes "nothing reached my ledger
without me seeing it" a property of the code.
"""

from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal

from django.db import transaction as db_transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.categories.models import Category, CategoryKind
from apps.core.jalali import (
    current_jalali_month,
    format_money,
    jalali_month_bounds,
    month_label,
    month_progress,
)
from apps.core.money import quantize_money
from apps.transactions.models import Transaction

from .banks import UNKNOWN_CODE, bank_label
from .models import (
    BatchStatus,
    ItemStatus,
    SmsImportBatch,
    SmsImportItem,
    SmsReminderDismissal,
)
from .parser import ParsedSms, parse_sms

# How far into a new month the reminder keeps showing. Ten days is about how
# long "last month's messages" stays a fresh question; after that it is noise.
REMINDER_WINDOW_DAYS = 10

# A separator line the user can paste between messages, in addition to a blank
# line. Documented on the import screen.
_SEPARATOR_RE = re.compile(r"^\s*(?:-{3,}|={3,}|\*{3,}|#{3,})\s*$")

# "از: بانک ملت" / "فرستنده: 20004861" — a sender line at the top of a block.
_SENDER_LINE_RE = re.compile(r"^\s*(?:از|فرستنده|from|sender)\s*[:：]\s*(.+?)\s*$", re.IGNORECASE)

# A bare sender token on its own line: a short code ("20004861"), an international
# number ("+989999987641"), or an alphanumeric ID ("MELLIBANK").
_BARE_SENDER_RE = re.compile(r"^(?:\+?\d[\d\s\-]{2,}|\d{3,}|[A-Za-z][A-Za-z0-9._\-]{2,})$")

# A line that is only a Persian/Arabic-Indic digit run is a message body, not a
# sender, even though it is short and numeric.
_PERSIAN_DIGITS_RE = re.compile(r"[\u06f0-\u06f9\u0660-\u0669]")
_PERSIAN_LETTERS_RE = re.compile(r"[\u0600-\u06ff]")


# --------------------------------------------------------------------------
# Splitting a pasted blob
# --------------------------------------------------------------------------


def _looks_like_sender(line: str) -> bool:
    """Whether a block's first line is a sender ID rather than message text."""
    if not line or len(line) > 40:
        return False
    # A line with Persian letters or Persian digits is message text — a bank's
    # Persian sentence pulled out of a phone app often starts on its own line.
    if _PERSIAN_LETTERS_RE.search(line) or _PERSIAN_DIGITS_RE.search(line):
        return False
    # A date/datetime stamp ("2026-09-06", "1405/06/15 07:28", "07:28") is part
    # of the body, not a sender — without this a leading stamp is swallowed as
    # the sender and the message loses its date.
    if re.search(r"\d\s*[/.\-]\s*\d", line) or re.search(r"\d\s*:\s*\d{2}", line):
        return False
    return bool(_BARE_SENDER_RE.match(line))


def split_messages(raw_text: str) -> list[tuple[str, str]]:
    """Split pasted text into ``[(sender, body), ...]``.

    Accepted separators, documented on the import screen:

    *   a blank line between messages (what a phone's message list copies as);
    *   a line of ``---`` (or ``===``, ``***``, ``###``).

    An optional first line naming the sender is picked up in two forms::

        از: بانک ملت
        مبلغ ۱,۵۰۰,۰۰۰ ریال به حساب شما واریز گردید.

        20004861
        -1,100,000
        مانده 17,712,600

    Both are optional. Pasted text with neither separator becomes one message,
    which is the right answer for a single-message paste and the only safe
    answer for anything ambiguous.
    """
    text = (raw_text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        return []

    blocks: list[list[str]] = [[]]
    for line in text.split("\n"):
        if _SEPARATOR_RE.match(line) or not line.strip():
            if blocks[-1]:
                blocks.append([])
            continue
        blocks[-1].append(line)

    messages: list[tuple[str, str]] = []
    for block in blocks:
        lines = [line.strip() for line in block if line.strip()]
        if not lines:
            continue

        sender = ""
        first = lines[0]

        explicit = _SENDER_LINE_RE.match(first)
        if explicit:
            sender = explicit.group(1).strip()
            lines = lines[1:]
        elif _looks_like_sender(first):
            sender = first
            lines = lines[1:]

        body = "\n".join(lines).strip()
        if body:
            messages.append((sender, body))

    return messages


def parse_messages(
    *, raw_text: str = "", messages: list[tuple[str, str]] | None = None
) -> list[ParsedSms]:
    """Parse either a pasted blob or an explicit list of ``(sender, body)``."""
    if messages is None:
        messages = split_messages(raw_text)
    return [parse_sms(body, sender=sender) for sender, body in messages]


# --------------------------------------------------------------------------
# Months
# --------------------------------------------------------------------------


def previous_period(today: dt.date | None = None) -> tuple[int, int]:
    """The Jalali ``(year, month)`` that just ended.

    This is the period the monthly reminder is about: on ۱ مهر the question is
    "did شهریور's messages get in?", not "what month is it?".
    """
    year, month = current_jalali_month(today)
    if month == 1:
        return year - 1, 12
    return year, month - 1


# --------------------------------------------------------------------------
# Category suggestion
# --------------------------------------------------------------------------
# Pairs of (words that hint at a category, names that category may go by). The
# second half is matched against the user's *own* category names, so nothing is
# invented: if a hint matches no category the user has, the row is simply left
# uncategorised. Only a suggestion ever prefilled — the user confirms it.
CATEGORY_KEYWORD_RULES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("رستوران", "کافه", "کافی شاپ", "فست فود", "فستفود", "پیتزا", "ساندویچ", "قهوه", "کباب", "نانوایی", "شیرینی", "سوپر", "هایپر"),
        ("خوراک", "رستوران", "کافه", "غذا", "سوپر"),
    ),
    (
        ("تاکسی", "اسنپ", "بنزین", "پمپ بنزین", "جایگاه", "مترو", "اتوبوس", "بلیت", "قطار", "پارکینگ", "تعمیرگاه", "لجستیک", "پست"),
        ("حمل", "خودرو", "سوخت", "بنزین", "تاکسی", "نقلیه", "سفر"),
    ),
    (
        ("داروخانه", "دارو", "درمان", "پزشک", "کلینیک", "بیمارستان", "آزمایشگاه", "دندانپزشک"),
        ("سلامت", "درمان", "دارو", "پزشک"),
    ),
    (("پوشاک", "لباس", "کفش", "کیف", "بوتیک"), ("پوشاک", "لباس", "خرید")),
    (
        ("همراه اول", "ایرانسل", "رایتل", "اینترنت", "بسته داده", "شارژ"),
        ("تلفن", "اینترنت", "ارتباطات", "موبایل", "شارژ"),
    ),
    (("برق", "گاز", "آب", "قبض", "عوارض"), ("قبض", "خانه", "انرژی", "شارژ")),
    (("اجاره", "رهن", "ودیعه"), ("مسکن", "خانه", "اجاره")),
    (("حقوق", "کارفرما", "معوقه"), ("حقوق", "درآمد", "دستمزد")),
    (("سود سهام", "بورس", "کارگزاری", "صندوق"), ("سرمایه", "سود", "بورس")),
    (("قسط", "وام", "تسهیلات", "اقساط", "بدهی"), ("بدهی", "وام", "اقساط", "تعهد")),
    (("کتاب", "دوره", "آموزش", "دانشگاه", "شهریه"), ("آموزش", "کتاب", "تحصیل", "دوره")),
    (("بازی", "سینما", "فیلم", "کنسرت", "اشتراک"), ("سرگرمی", "تفریح", "اشتراک")),
)


def suggest_category(user, *, haystack: str, direction: str | None):
    """A best-guess category for a parsed message, or ``None``.

    Two passes, cheapest first:

    1.  A category the user already owns whose **name appears in the message**.
        This is what makes the "پذیرنده: فروشگاه رفاه" case work for a user whose
        category is literally نام‌گذاری‌شده, with no keyword table involved.
    2.  The keyword rules above, matched against the user's category names.

    Only ever a suggestion: a wrong guess costs one tap to change, and leaving
    every row blank would make the review screen a data-entry chore — which is
    the thing this feature exists to remove.
    """
    if not haystack:
        return None

    kind = CategoryKind.INCOME if direction == "income" else CategoryKind.EXPENSE
    categories = list(
        Category.objects.filter(user=user, kind=kind, is_active=True).order_by("sort_order", "name")
    )
    if not categories:
        return None

    for category in categories:
        if category.name and category.name in haystack:
            return category

    for keywords, hints in CATEGORY_KEYWORD_RULES:
        if not any(keyword in haystack for keyword in keywords):
            continue
        for category in categories:
            if any(hint in category.name for hint in hints):
                return category

    return None


# Words in a bank label that carry no identity ("بانک قرض‌الحسنه مهر ایران" is
# about "مهر ایران", not about "بانک"). Used to match an SMS against the user's
# accounts by their `institution`/`name`.
_BANK_LABEL_STOPWORDS = frozenset({"بانک", "و", "قرض‌الحسنه", "قرض", "الحسنه"})


def _bank_tokens(bank_code: str) -> list[str]:
    """Identity words of a bank label, for account matching."""
    label = bank_label(bank_code)
    parts = re.split(r"[\s()\[\]<>«»]+", label)
    tokens = [part for part in parts if part and part not in _BANK_LABEL_STOPWORDS]
    if bank_code == "blubank" and "بلو" not in tokens:
        tokens.append("بلو")
    return tokens


def suggest_account(user, *, bank_code: str):
    """The user's account this bank's messages most likely belong to, or None.

    Matches the bank's identity words against the user's accounts
    (`institution` first, then `name`) and only answers when the match is
    **unique**: with two "ملت" accounts, guessing one would file money under
    the wrong card. A suggestion is prefilled on the review screen — the user
    still confirms it before anything reaches the ledger.
    """
    from apps.accounts.models import Account

    if not bank_code or bank_code == UNKNOWN_CODE:
        return None
    tokens = _bank_tokens(bank_code)
    if not tokens:
        return None

    accounts = list(
        Account.objects.filter(user=user, is_active=True).order_by("sort_order", "name")
    )
    if not accounts:
        return None

    def hits(field: str) -> list:
        matched = []
        for account in accounts:
            value = getattr(account, field, "") or ""
            if any(token and token in value for token in tokens):
                matched.append(account)
        return matched

    for field in ("institution", "name"):
        matched = hits(field)
        unique = list(dict.fromkeys(matched))
        if len(unique) == 1:
            return unique[0]
    return None


# --------------------------------------------------------------------------
# Staging
# --------------------------------------------------------------------------

ALREADY_IMPORTED_WARNING = (
    "این پیامک پیش از این وارد شده است؛ برای جلوگیری از ثبت دوباره، تکراری علامت خورده است."
)
POSSIBLE_DUPLICATE_WARNING = (
    "پیامکی با همین مبلغ و تاریخ قبلاً ثبت شده است؛ اگر همان تراکنش است، این قلم را رد کنید."
)
OUT_OF_PERIOD_WARNING = "تاریخ این پیامک در ماه انتخاب‌شده نیست."


def _soft_duplicate_exists(user, batch: SmsImportBatch, parsed: ParsedSms) -> bool:
    """Whether an *imported* row with the same amount and date already exists.

    A weaker check than the fingerprint: two differently-worded messages about
    the same purchase (a POS receipt and a bank notice) hash differently but
    describe the same money. This produces a warning rather than a duplicate
    status, because two genuinely identical purchases on one day are real.
    """
    if parsed.amount_toman is None or parsed.occurred_on is None:
        return False

    query = (
        SmsImportItem.objects.filter(
            user=user,
            status=ItemStatus.IMPORTED,
            amount=parsed.amount_toman,
            occurred_on=parsed.occurred_on,
        )
        .exclude(batch=batch)
    )
    if parsed.direction:
        query = query.filter(direction=parsed.direction)
    return query.exists()


def _build_item(
    user, batch: SmsImportBatch, parsed: ParsedSms, seen: set[str]
) -> SmsImportItem | None:
    """Turn one parsed message into a staged row, flagging duplicates.

    A message pasted twice into the *same* batch is not staged twice: the
    ``unique_fingerprint_per_batch`` constraint forbids it, and one row is what
    the user needs. A message already staged in an *earlier* batch is staged
    again and marked ``duplicate``, because re-importing a month must stay
    possible — flagged, not silently dropped.
    """
    if parsed.fingerprint in seen:
        return None
    seen.add(parsed.fingerprint)

    warnings = list(parsed.warnings)
    status = ItemStatus.PENDING
    if (
        SmsImportItem.objects.filter(user=user, fingerprint=parsed.fingerprint)
        .exclude(batch=batch)
        .exclude(status=ItemStatus.SKIPPED)
        .exists()
    ):
        status = ItemStatus.DUPLICATE
        warnings.append(ALREADY_IMPORTED_WARNING)
    elif _soft_duplicate_exists(user, batch, parsed):
        warnings.append(POSSIBLE_DUPLICATE_WARNING)

    if parsed.occurred_on is not None:
        first, last = jalali_month_bounds(batch.period_year, batch.period_month)
        if not (first <= parsed.occurred_on <= last):
            warnings.append(OUT_OF_PERIOD_WARNING)

    haystack = " ".join(part for part in (parsed.merchant, parsed.normalized) if part)
    # A category is only suggested for a row that already has a direction and an
    # amount — suggesting one for an unreadable message would put a label on
    # nothing.
    category = (
        suggest_category(user, haystack=haystack, direction=parsed.direction)
        if parsed.is_usable
        else None
    )
    # The batch account wins when the user set one; otherwise prefill the one
    # account whose institution matches the detected bank — still just a
    # suggestion the review screen can change before commit.
    account = batch.account or (
        suggest_account(user, bank_code=parsed.bank_code) if parsed.is_usable else None
    )

    return SmsImportItem.objects.create(
        batch=batch,
        user=user,
        raw_text=parsed.raw_text,
        sender=parsed.sender,
        bank=parsed.bank_code,
        bank_label=parsed.bank_label,
        fingerprint=parsed.fingerprint,
        is_transaction=parsed.is_transaction,
        noise_kind=parsed.noise_kind,
        direction=parsed.direction or "",
        direction_pattern=parsed.direction_pattern,
        amount=parsed.amount_toman,
        amount_unit=parsed.amount_unit,
        amount_unit_assumed=parsed.amount_was_assumed,
        balance_after=parsed.balance_after,
        balance_label=parsed.balance_label,
        occurred_on=parsed.occurred_on,
        date_source=parsed.date_source,
        confidence=parsed.confidence,
        field_confidence={key: str(value) for key, value in parsed.field_confidence.items()},
        card_last4=parsed.card_last4,
        merchant=parsed.merchant,
        warnings=warnings,
        category=category,
        account=account,
        spending_type="",
        description=parsed.description,
        status=status,
    )


@db_transaction.atomic
def create_batch(
    user,
    *,
    raw_text: str = "",
    messages: list[tuple[str, str]] | None = None,
    period_year: int | None = None,
    period_month: int | None = None,
    source_label: str = "",
    account=None,
) -> SmsImportBatch:
    """Parse messages and stage them as a reviewable batch.

    Defaults to the previous Jalali month, because that is the monthly flow this
    module exists for: at the start of a month, the messages you have just
    finished collecting are last month's.
    """
    if period_year is None or period_month is None:
        period_year, period_month = previous_period()

    parsed_list = parse_messages(raw_text=raw_text, messages=messages)

    batch = SmsImportBatch.objects.create(
        user=user,
        period_year=period_year,
        period_month=period_month,
        source_label=(source_label or "")[:120],
        account=account,
    )

    seen: set[str] = set()
    for parsed in parsed_list:
        _build_item(user, batch, parsed, seen)

    return batch


# --------------------------------------------------------------------------
# Committing to the ledger
# --------------------------------------------------------------------------


@db_transaction.atomic
def commit_batch(user, batch: SmsImportBatch, item_ids: list[int] | None = None) -> dict:
    """Create the `Transaction` rows for the items the user confirmed.

    Only complete rows — direction, amount and category — become transactions.
    Anything else stays ``pending`` and is counted in the response, so the UI can
    say *why* nothing was written instead of importing a partial ledger:

    *   ``missing_category`` — no category chosen yet;
    *   ``incomplete`` — no amount or no direction could be read;
    *   ``not_transaction`` — a message the parser rejected as noise.

    An item with no parsed date is committed on the **first day of the batch's
    period** and marked ``date_source="assumed"``. That is a stated convention
    rather than a silent one: the user grouped those messages into that month,
    and a message with no date cannot be placed more precisely than that.
    """
    if batch.user_id != user.id:
        raise ValueError("این دسته به شما تعلق ندارد.")

    items = batch.items.select_related("category", "account").all()
    if item_ids is not None:
        items = items.filter(id__in=item_ids)
    items = list(items)

    period_start, _ = jalali_month_bounds(batch.period_year, batch.period_month)

    created: list[Transaction] = []
    missing_category = 0
    incomplete = 0
    not_transaction = 0

    for item in items:
        if item.status != ItemStatus.PENDING:
            continue
        if not item.is_transaction:
            not_transaction += 1
            continue
        if item.amount is None or not item.direction:
            incomplete += 1
            continue
        if not item.category_id:
            missing_category += 1
            continue

        occurred_on = item.occurred_on or period_start
        transaction = Transaction.objects.create(
            user=user,
            transaction_type=item.direction,
            amount=item.amount,
            category=item.category,
            account=item.account or batch.account,
            occurred_on=occurred_on,
            description=(item.description or "")[:200],
            note=item.note or "",
            spending_type=item.spending_type or "",
        )

        item.transaction = transaction
        item.status = ItemStatus.IMPORTED
        if item.occurred_on is None:
            item.occurred_on = occurred_on
            item.date_source = "assumed"
        item.save(
            update_fields=[
                "transaction",
                "status",
                "occurred_on",
                "date_source",
                "updated_at",
            ]
        )
        created.append(transaction)

    if created and batch.status != BatchStatus.COMMITTED:
        batch.status = BatchStatus.COMMITTED
        batch.committed_at = timezone.now()
        batch.save(update_fields=["status", "committed_at", "updated_at"])

    return {
        "batch": batch,
        "imported_count": len(created),
        "missing_category_count": missing_category,
        "incomplete_count": incomplete,
        "not_transaction_count": not_transaction,
        "transactions": created,
    }


# --------------------------------------------------------------------------
# Balance reconciliation
# --------------------------------------------------------------------------


def balance_reconciliation(user, batch: SmsImportBatch) -> dict:
    """What the balance printed in an SMS implies about the account.

    Balances in this app are derived — ``opening_balance + income - expense``
    (see `apps.accounts.models`) — so an SMS balance is never written into a
    balance column. It answers a more useful question instead: *what would the
    opening balance have to be for the ledger to agree with the bank?*

    The newest balance reading in the batch is the anchor. Every transaction on
    the account **after** that reading moves the balance, so::

        implied_opening = reading - (income_after - expense_after)

    A difference from the account's stored ``opening_balance`` is real
    information: a missing transaction, a double-counted one, or an opening
    balance that was never set. Nothing is written here —
    :func:`apply_balance_reconciliation` does that, and only on request.
    """
    account = batch.account
    if account is None:
        return {
            "available": False,
            "message": "برای تطبیق موجودی، ابتدا حساب این دسته را انتخاب کنید.",
        }
    if account.user_id != user.id:
        return {
            "available": False,
            "message": "این حساب به شما تعلق ندارد.",
        }

    readings = [item for item in batch.items.all() if item.balance_after is not None]
    if not readings:
        return {
            "available": False,
            "message": "در پیامک‌های این دسته موجودی‌ای خوانده نشد؛ چیزی برای تطبیق نیست.",
        }

    latest = max(readings, key=lambda item: (item.occurred_on or dt.date.min, item.id))

    later = account.transactions.filter(user_id=user.id)
    if latest.occurred_on is not None:
        later = later.filter(occurred_on__gt=latest.occurred_on)

    totals = later.aggregate(
        income=Sum("amount", filter=Q(transaction_type="income")),
        expense=Sum("amount", filter=Q(transaction_type="expense")),
    )
    income = quantize_money(totals["income"] or Decimal("0"))
    expense = quantize_money(totals["expense"] or Decimal("0"))

    implied_opening = quantize_money(latest.balance_after - (income - expense))
    drift = quantize_money(implied_opening - account.opening_balance)

    return {
        "available": True,
        "account_id": account.pk,
        "account_name": account.name,
        "reading_amount": latest.balance_after,
        "reading_amount_display": format_money(latest.balance_after),
        "reading_date": latest.occurred_on,
        "reading_label": latest.balance_label,
        "later_income": income,
        "later_expense": expense,
        "implied_opening_balance": implied_opening,
        "implied_opening_balance_display": format_money(implied_opening),
        "current_opening_balance": quantize_money(account.opening_balance),
        "current_opening_balance_display": format_money(account.opening_balance),
        "drift": drift,
        "drift_display": format_money(abs(drift)),
        "matches": drift == 0,
        "message": (
            "موجودی اعلام‌شده با دفتر شما می‌خواند."
            if drift == 0
            else "موجودی اعلام‌شده با دفتر شما اختلاف دارد؛ می‌توانید موجودی اولیه حساب را هماهنگ کنید."
        ),
    }


@db_transaction.atomic
def apply_balance_reconciliation(user, batch: SmsImportBatch) -> dict:
    """Set the account's opening balance from the newest SMS reading."""
    result = balance_reconciliation(user, batch)
    if not result.get("available"):
        return result

    account = batch.account
    account.opening_balance = result["implied_opening_balance"]
    account.save(update_fields=["opening_balance", "updated_at"])

    result["applied"] = True
    result["message"] = "موجودی اولیه حساب بر پایه پیامک‌ها تنظیم شد."
    return result


# --------------------------------------------------------------------------
# The monthly reminder
# --------------------------------------------------------------------------


def reminder_state(user, today: dt.date | None = None) -> dict:
    """Whether to prompt the user to import last month's messages.

    The prompt is about the month that just ended, and it stops for three
    reasons, each of which is a distinct message on screen:

    *   the batch for that month is already committed — the job is done;
    *   the user dismissed it for that month;
    *   the window (``REMINDER_WINDOW_DAYS`` days into the new month) has passed.

    The window exists so a stale prompt does not follow the user around all
    month. Dismissal is stored per period (see `SmsReminderDismissal`) rather
    than on a batch, so it can be dismissed without importing anything.
    """
    today = today or dt.date.today()
    year, month = current_jalali_month(today)
    period_year, period_month = previous_period(today)

    progress = month_progress(year, month, today)

    batches = SmsImportBatch.objects.filter(
        user=user, period_year=period_year, period_month=period_month
    )
    has_batch = batches.exists()
    has_committed_batch = batches.filter(status=BatchStatus.COMMITTED).exists()
    dismissed = SmsReminderDismissal.objects.filter(
        user=user, period_year=period_year, period_month=period_month
    ).exists()

    pending_count = SmsImportItem.objects.filter(
        user=user,
        status=ItemStatus.PENDING,
        is_transaction=True,
        batch__period_year=period_year,
        batch__period_month=period_month,
    ).count()

    within_window = progress["days_elapsed"] <= REMINDER_WINDOW_DAYS
    should_remind = bool(within_window and not dismissed and not has_committed_batch)

    if has_committed_batch:
        message = "پیامک‌های ماه گذشته ثبت شده است."
    elif pending_count:
        message = "در پیامک‌های ماه گذشته قلم‌های بررسی‌نشده باقی مانده است."
    else:
        message = (
            f"ماه {month_label(period_year, period_month)} تمام شد؛ "
            "پیامک‌های بانکی آن را وارد کنید تا تراکنش‌ها و موجودی‌ها ثبت شود."
        )

    return {
        "should_remind": should_remind,
        "dismissed": dismissed,
        "within_window": within_window,
        "window_days": REMINDER_WINDOW_DAYS,
        "current_year": year,
        "current_month": month,
        "current_label": month_label(year, month),
        "days_elapsed": progress["days_elapsed"],
        "suggested_year": period_year,
        "suggested_month": period_month,
        "suggested_label": month_label(period_year, period_month),
        "has_batch": has_batch,
        "has_committed_batch": has_committed_batch,
        "pending_count": pending_count,
        "message": message,
    }


def dismiss_reminder(user, period_year: int, period_month: int) -> SmsReminderDismissal:
    """Hide the reminder for one period. Idempotent."""
    dismissal, _ = SmsReminderDismissal.objects.get_or_create(
        user=user, period_year=period_year, period_month=period_month
    )
    return dismissal


# --------------------------------------------------------------------------
# Bulk review
# --------------------------------------------------------------------------


@db_transaction.atomic
def bulk_update_items(user, items, **fields) -> dict:
    """Apply the same decision to many staged items at once.

    Reviewing sixty messages one at a time is the reason a feature like this gets
    abandoned, so assigning a category to a whole selection in one request is
    part of the design rather than a convenience.

    A category is only applied to items whose direction matches its kind. The
    mismatches are counted instead of raising, because a mixed selection is
    normal (a month contains salaries and groceries) and failing the whole
    request would make the bulk action useless on exactly the selection it is
    most needed for.
    """
    allowed = {"category", "account", "spending_type", "status", "description"}
    fields = {key: value for key, value in fields.items() if key in allowed}

    category = fields.get("category")
    updated = 0
    skipped = 0

    for item in items:
        if item.user_id != user.id:
            skipped += 1
            continue

        if category is not None and item.direction:
            expected = (
                CategoryKind.INCOME if item.direction == "income" else CategoryKind.EXPENSE
            )
            if category.kind != expected:
                skipped += 1
                continue

        for key, value in fields.items():
            if key == "spending_type" and item.direction == "income":
                # Never classify an income row; `Transaction.save()` would clear
                # it anyway, and storing it would be a lie until then.
                continue
            setattr(item, key, value)

        item.save()
        updated += 1

    return {"updated_count": updated, "skipped_count": skipped}







