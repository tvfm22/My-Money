"""Aggregations over transactions that more than one screen needs.

The essential / flexible / wasted split is shown in three places — the
dashboard, the reports page and (later) the budget drill-down — and all three
must agree to the Toman. Computing it in one function is what makes that true;
three inline ``Sum`` calls in three views is how they would drift.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db.models import Count, Sum

from apps.core.jalali import format_money, format_percent
from apps.core.money import ZERO, percentage, quantize_money, sum_money

from .models import SpendingType, Transaction, TransactionType

# Fixed order, always all three, even at zero. A stable shape means the UI does
# not have to guess which buckets exist, and an explicit «هدر رفته: ۰ تومان» is
# information — it says the user looked and found none.
SPENDING_TYPE_ORDER: tuple[str, ...] = (
    SpendingType.ESSENTIAL,
    SpendingType.FLEXIBLE,
    SpendingType.WASTED,
)

# The key used for expenses that carry no classification at all.
UNCLASSIFIED = ""


def _bucket(key: str, label: str, amount: Decimal, count: int, total: Decimal) -> dict:
    """One bucket, with both the raw value and the pre-formatted display string.

    Both, not one: the client renders the display string so the two sides cannot
    disagree, but the raw string is what the API contract is actually about and
    what a test should assert against.
    """
    share = percentage(amount, total)
    return {
        "key": key,
        "label": label,
        "amount": str(amount),
        "amount_display": format_money(amount),
        "share_percent": str(share),
        "share_display": format_percent(share),
        "transaction_count": count,
    }


def build_buckets(
    by_type: dict[str, tuple[Decimal, int]], total: Decimal
) -> list[dict]:
    """Shape a ``{spending_type: (amount, count)}`` map into the bucket list.

    Shared by the whole-month split and the per-category split. Two copies of
    this loop is exactly how the same number ends up formatted two different
    ways on two screens.
    """
    buckets = [
        _bucket(
            key,
            SpendingType(key).label,
            *by_type.get(key, (ZERO, 0)),
            total,
        )
        for key in SPENDING_TYPE_ORDER
    ]

    # An expense with no classification can only exist if a row was written
    # outside `save()`. Surface it rather than hiding it inside the total, so a
    # silent gap cannot masquerade as a complete split.
    amount, count = by_type.get(UNCLASSIFIED, (ZERO, 0))
    if amount > 0:
        buckets.append(_bucket(UNCLASSIFIED, "دسته‌بندی نشده", amount, count, total))

    return buckets


def spending_type_breakdown(
    user,
    start: dt.date,
    end: dt.date,
) -> dict:
    """Split a user's expenses in a date range by their own classification.

    Only expenses are counted: income carries no classification, so including it
    would put a phantom bucket in the payload.

    Returns a payload with both raw decimal strings and pre-formatted display
    strings, matching the rest of the API — the client renders the display
    strings so the two sides can never disagree about an amount.
    """
    rows = (
        Transaction.objects.for_user(user)
        .filter(
            transaction_type=TransactionType.EXPENSE,
            occurred_on__gte=start,
            occurred_on__lte=end,
        )
        .values("spending_type")
        .annotate(total=Sum("amount"), count=Count("id"))
    )

    by_type: dict[str, tuple[Decimal, int]] = {
        row["spending_type"]: (quantize_money(row["total"]), row["count"])
        for row in rows
    }

    total = quantize_money(
        sum_money([amount for amount, _count in by_type.values()])
    )

    return {
        "total": str(total),
        "total_display": format_money(total),
        "buckets": build_buckets(by_type, total),
        "start": start.isoformat(),
        "end": end.isoformat(),
    }


def spending_type_by_category(
    user,
    start: dt.date,
    end: dt.date,
) -> dict[int, dict]:
    """Per-category split, keyed by category id, for the budget drill-down.

    One grouped query for the whole range rather than one query per category:
    the budgets screen shows every category at once, so a per-row query would be
    N+1 on the most frequently opened page in the app.

    Child spending is rolled into its parent's buckets, mirroring
    ``apps.budgets.services.spent_by_category``. That is not a detail — it is
    what makes the split shown in the drill-down add up to the ``spent`` figure
    printed next to it. Two different roll-up rules would produce a panel whose
    parts do not sum to its own heading.
    """
    rows = (
        Transaction.objects.for_user(user)
        .filter(
            transaction_type=TransactionType.EXPENSE,
            occurred_on__gte=start,
            occurred_on__lte=end,
        )
        .values("category_id", "category__parent_id", "spending_type")
        .annotate(total=Sum("amount"), count=Count("id"))
    )

    # category_id -> spending_type -> [amount, count]
    grouped: dict[int, dict[str, list]] = {}

    def _add(category_id: int, spending_type: str, amount: Decimal, count: int) -> None:
        by_type = grouped.setdefault(category_id, {})
        current = by_type.setdefault(spending_type, [ZERO, 0])
        current[0] = current[0] + amount
        current[1] = current[1] + count

    for row in rows:
        category_id = row["category_id"]
        if category_id is None:
            continue

        amount = quantize_money(row["total"])
        count = row["count"]
        spending_type = row["spending_type"]

        # Attribute the spend to the category itself...
        _add(category_id, spending_type, amount, count)

        # ...and roll it up to the parent so a parent-level budget line sees it.
        parent_id = row["category__parent_id"]
        if parent_id is not None:
            _add(parent_id, spending_type, amount, count)

    result: dict[int, dict] = {}
    for category_id, by_type in grouped.items():
        normalised = {key: (value[0], value[1]) for key, value in by_type.items()}
        total = quantize_money(
            sum_money([amount for amount, _count in normalised.values()])
        )
        result[category_id] = {
            "total": str(total),
            "total_display": format_money(total),
            "buckets": build_buckets(normalised, total),
        }

    return result
