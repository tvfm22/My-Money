"""Budget analysis — the calculation engine behind the whole budgeting feature.

This module is the single place where "how am I doing against my budget?" is
answered. Keeping it server-side means the web client, and any future mobile
client, cannot disagree about the numbers, and the logic is testable without a
browser.

Design principles
-----------------
1.  **Spending is always derived from real transactions.** Never cached, never
    estimated. If the user deleted a transaction, the next read reflects it.

2.  **Pace is compared, not judged.** The core insight is that spending 40% of a
    budget when 60% of the month has passed is a *different* situation from
    spending 65% when 40% has passed. The comparison is arithmetic; the wording
    is neutral and never scolds the user (see `PACE_MESSAGES`).

3.  **Overspending is reported, not hidden.** A budget can be over 100%
    consumed, and the UI needs to say so plainly rather than clamping to 100.

4.  **No financial advice.** The app reports "این دسته از روند ماهانه جلوتر است",
    never "شما باید کمتر خرج کنید".
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Count, Sum

from apps.core.jalali import jalali_month_bounds, month_progress
from apps.core.money import ZERO, percentage, quantize_money, safe_divide

# ---------------------------------------------------------------------------
# Status vocabulary
#
# These four states are the entire shared language between backend and UI.
# They are thresholds on budget consumption, deliberately generous at the
# "safe" end: a user who has spent a little more than time elapsed should not
# see a warning, or the alert becomes noise and gets ignored.
# ---------------------------------------------------------------------------

STATUS_SAFE = "safe"
STATUS_NORMAL = "normal"
STATUS_NEAR_LIMIT = "near_limit"
STATUS_OVER = "over"

STATUS_LABELS = {
    STATUS_SAFE: "در محدوده بودجه",
    STATUS_NORMAL: "مصرف معمولی",
    STATUS_NEAR_LIMIT: "نزدیک به سقف بودجه",
    STATUS_OVER: "بیشتر از بودجه",
}

# How far consumption may run ahead of elapsed time before we change the
# message. 15 percentage points is roughly "half a week ahead" on a 30-day
# month — enough to be real signal, small enough not to fire on a single big
# purchase.
PACE_TOLERANCE = Decimal("15")

# Consumption thresholds for the status ladder.
NEAR_LIMIT_THRESHOLD = Decimal("80")
OVER_THRESHOLD = Decimal("100")


@dataclass
class CategoryBudgetAnalysis:
    """Everything computed about one budgeted category in one month."""

    category_id: int
    category_name: str
    category_icon: str
    category_color: str
    category_full_path: str
    is_essential: bool

    budgeted: Decimal
    spent: Decimal
    remaining: Decimal

    # Percentages (0..N, can exceed 100).
    consumed_percent: Decimal
    # Percentage of the whole month that has elapsed.
    elapsed_percent: Decimal

    # Difference between consumption and elapsed time. Positive means the
    # category is being consumed faster than the month is passing.
    pace_delta: Decimal

    status: str
    status_label: str
    pace_state: str  # "behind" | "on_track" | "ahead"
    message: str

    # Projection: where this category lands by month end if the current daily
    # rate holds. Only meaningful mid-month, and explicitly labelled as an
    # extrapolation in the UI rather than a prediction.
    projected_total: Decimal | None
    projected_over_budget: bool

    transaction_count: int = 0
    days_elapsed: int = 0
    days_in_month: int = 0

    def to_dict(self) -> dict:
        from apps.core.jalali import format_money, format_percent

        return {
            "category_id": self.category_id,
            "category_name": self.category_name,
            "category_icon": self.category_icon,
            "category_color": self.category_color,
            "category_full_path": self.category_full_path,
            "is_essential": self.is_essential,
            "budgeted": str(quantize_money(self.budgeted)),
            "spent": str(quantize_money(self.spent)),
            "remaining": str(quantize_money(self.remaining)),
            "consumed_percent": str(self.consumed_percent),
            "elapsed_percent": str(self.elapsed_percent),
            "pace_delta": str(self.pace_delta),
            "status": self.status,
            "status_label": self.status_label,
            "pace_state": self.pace_state,
            "message": self.message,
            "projected_total": (
                str(quantize_money(self.projected_total))
                if self.projected_total is not None
                else None
            ),
            "projected_over_budget": self.projected_over_budget,
            "transaction_count": self.transaction_count,
            "days_elapsed": self.days_elapsed,
            "days_in_month": self.days_in_month,
            # Pre-formatted strings so the client renders identical text to the
            # server's own reasoning.
            "budgeted_display": format_money(self.budgeted),
            "spent_display": format_money(self.spent),
            "remaining_display": format_money(self.remaining),
            "consumed_display": format_percent(self.consumed_percent),
            "elapsed_display": format_percent(self.elapsed_percent),
            "progress_ratio": str(min(self.consumed_percent / Decimal("100"), Decimal("1"))),
            "over_budget_amount": str(
                quantize_money(max(self.spent - self.budgeted, ZERO))
            ),
            # These two were the only money fields in this payload without a
            # display sibling, which left the client formatting them itself —
            # against the rule that the server owns the rendered figure so the
            # two sides cannot disagree. `projected_display` mirrors the None on
            # `projected_total` rather than inventing a value.
            "over_budget_display": format_money(
                max(self.spent - self.budgeted, ZERO)
            ),
            "projected_display": (
                format_money(self.projected_total)
                if self.projected_total is not None
                else None
            ),
        }


@dataclass
class BudgetAnalysis:
    """The complete analysis of one month's budget."""

    budget_id: int | None
    year: int
    month: int
    month_name: str
    label: str

    # Plan
    expected_income: Decimal
    savings_target: Decimal
    investment_target: Decimal
    debt_payment_target: Decimal
    flexible_budget: Decimal
    is_oversubscribed: bool

    # Actuals
    total_budgeted: Decimal
    total_spent: Decimal
    total_remaining: Decimal
    total_consumed_percent: Decimal

    # Time context
    days_elapsed: int
    days_in_month: int
    days_remaining: int
    elapsed_percent: Decimal

    categories: list[CategoryBudgetAnalysis] = field(default_factory=list)

    # Breakdown of where planned income goes (spec section 12).
    essential_total: Decimal = ZERO
    flexible_total: Decimal = ZERO

    # Month-level comparisons against real recorded transactions.
    actual_income: Decimal = ZERO
    actual_expense: Decimal = ZERO

    has_budget: bool = True
    has_items: bool = True

    def to_dict(self) -> dict:
        from apps.core.jalali import format_money, format_percent

        return {
            "budget_id": self.budget_id,
            "year": self.year,
            "month": self.month,
            "month_name": self.month_name,
            "label": self.label,
            "has_budget": self.has_budget,
            "has_items": self.has_items,
            "plan": {
                "expected_income": str(quantize_money(self.expected_income)),
                "savings_target": str(quantize_money(self.savings_target)),
                "investment_target": str(quantize_money(self.investment_target)),
                "debt_payment_target": str(quantize_money(self.debt_payment_target)),
                "flexible_budget": str(quantize_money(self.flexible_budget)),
                "is_oversubscribed": self.is_oversubscribed,
                "essential_total": str(quantize_money(self.essential_total)),
                "flexible_total": str(quantize_money(self.flexible_total)),
                "expected_income_display": format_money(self.expected_income),
                "savings_target_display": format_money(self.savings_target),
                "investment_target_display": format_money(self.investment_target),
                "debt_payment_target_display": format_money(self.debt_payment_target),
                "flexible_budget_display": format_money(self.flexible_budget),
                "essential_total_display": format_money(self.essential_total),
                "flexible_total_display": format_money(self.flexible_total),
            },
            "totals": {
                "budgeted": str(quantize_money(self.total_budgeted)),
                "spent": str(quantize_money(self.total_spent)),
                "remaining": str(quantize_money(self.total_remaining)),
                "consumed_percent": str(self.total_consumed_percent),
                "budgeted_display": format_money(self.total_budgeted),
                "spent_display": format_money(self.total_spent),
                "remaining_display": format_money(self.total_remaining),
                "consumed_display": format_percent(self.total_consumed_percent),
                "progress_ratio": str(
                    min(self.total_consumed_percent / Decimal("100"), Decimal("1"))
                ),
            },
            "actuals": {
                "income": str(quantize_money(self.actual_income)),
                "expense": str(quantize_money(self.actual_expense)),
                "net": str(quantize_money(self.actual_income - self.actual_expense)),
                "income_display": format_money(self.actual_income),
                "expense_display": format_money(self.actual_expense),
            },
            "time": {
                "days_elapsed": self.days_elapsed,
                "days_in_month": self.days_in_month,
                "days_remaining": self.days_remaining,
                "elapsed_percent": str(self.elapsed_percent),
                "elapsed_display": format_percent(self.elapsed_percent),
            },
            "categories": [item.to_dict() for item in self.categories],
        }


# ---------------------------------------------------------------------------
# Status / pace classification
# ---------------------------------------------------------------------------


def classify_status(consumed_percent: Decimal, spent: Decimal) -> str:
    """Map budget consumption onto the four-state ladder.

    Thresholds are on consumption alone, not on pace, because status answers
    "how close to the ceiling am I?" while pace answers "how fast am I getting
    there?". Keeping them independent means the UI can show both without one
    masking the other.
    """
    if spent <= 0:
        return STATUS_SAFE
    if consumed_percent > OVER_THRESHOLD:
        return STATUS_OVER
    if consumed_percent >= NEAR_LIMIT_THRESHOLD:
        return STATUS_NEAR_LIMIT
    if consumed_percent < NEAR_LIMIT_THRESHOLD / 2:
        return STATUS_SAFE
    return STATUS_NORMAL


def classify_pace(consumed_percent: Decimal, elapsed_percent: Decimal) -> str:
    """Compare consumption against time elapsed.

    Returns one of:
        ``behind``    — spending slower than the month is passing (good news)
        ``on_track``  — within tolerance either way
        ``ahead``     — spending faster than the month is passing
    """
    delta = consumed_percent - elapsed_percent

    if delta > PACE_TOLERANCE:
        return "ahead"
    if delta < -PACE_TOLERANCE:
        return "behind"
    return "on_track"


# Neutral, non-judgmental phrasing. Every message describes a *situation*;
# none of them comment on the user's character or give advice.
PACE_MESSAGES = {
    "behind": "وضعیت مناسب — مصرف شما از سرعت گذر ماه کمتر است.",
    "on_track": "مصرف شما هم‌راستا با روند ماه پیش می‌رود.",
    "ahead": "توجه — سرعت مصرف این بودجه بیشتر از روند ماهانه است.",
}

NEAR_LIMIT_MESSAGE = "بیشتر بودجه این دسته مصرف شده و به سقف نزدیک است."
OVER_MESSAGE = "بودجه تعیین‌شده برای این دسته تمام شده است."
NO_SPEND_MESSAGE = "هنوز هزینه‌ای در این دسته ثبت نشده است."
AHEAD_AND_NEAR = "هم به سقف بودجه نزدیک شده‌اید و هم سرعت مصرف بالاتر از روند ماه است."


def build_message(
    status: str,
    pace_state: str,
    has_spend: bool,
    consumed_percent: Decimal,
    elapsed_percent: Decimal,
) -> str:
    """Compose the one-line human explanation shown next to a budget.

    Ordering of concern: being over budget matters more than being ahead of
    pace, so it wins when both apply. Within that, the message stays factual.
    """
    if not has_spend:
        return NO_SPEND_MESSAGE

    if status == STATUS_OVER:
        return OVER_MESSAGE

    if status == STATUS_NEAR_LIMIT and pace_state == "ahead":
        return AHEAD_AND_NEAR

    if status == STATUS_NEAR_LIMIT:
        return NEAR_LIMIT_MESSAGE

    return PACE_MESSAGES.get(pace_state, PACE_MESSAGES["on_track"])


# ---------------------------------------------------------------------------
# Spending aggregation
# ---------------------------------------------------------------------------


def spent_by_category(user, start: dt.date, end: dt.date) -> dict[int, tuple[Decimal, int]]:
    """Total expense per category in a date range.

    Returns ``{category_id: (total, transaction_count)}``.

    Includes both direct spending and spending on child categories: if the user
    budgets "خوراک", purchases recorded under "میوه و سبزیجات" belong to that
    budget. This is what makes budgeting by parent category actually work.
    """
    from apps.transactions.models import Transaction, TransactionType

    # One grouped query does all the work; the parent roll-up happens in Python
    # over the already-fetched rows, so this stays a single query no matter how
    # many transactions or categories exist.
    rows = (
        Transaction.objects.for_user(user)
        .filter(
            transaction_type=TransactionType.EXPENSE,
            occurred_on__gte=start,
            occurred_on__lte=end,
        )
        .values("category_id", "category__parent_id")
        .annotate(total=Sum("amount"), n=Count("id"))
    )

    totals: dict[int, Decimal] = {}
    counts: dict[int, int] = {}

    for row in rows:
        category_id = row["category_id"]
        if category_id is None:
            continue

        parent_id = row["category__parent_id"]
        amount = quantize_money(row["total"])
        n = row["n"]

        # Attribute the spend to the category itself.
        totals[category_id] = totals.get(category_id, ZERO) + amount
        counts[category_id] = counts.get(category_id, 0) + n

        # And roll it up to the parent so parent-level budgets see it.
        if parent_id is not None:
            totals[parent_id] = totals.get(parent_id, ZERO) + amount
            counts[parent_id] = counts.get(parent_id, 0) + n

    return {key: (totals[key], counts.get(key, 0)) for key in totals}


def month_actuals(user, start: dt.date, end: dt.date) -> tuple[Decimal, Decimal]:
    """Actual recorded (income, expense) for a date range."""
    from apps.transactions.models import Transaction, TransactionType

    rows = (
        Transaction.objects.for_user(user)
        .filter(occurred_on__gte=start, occurred_on__lte=end)
        .values("transaction_type")
        .annotate(total=Sum("amount"))
    )

    income = ZERO
    expense = ZERO
    for row in rows:
        if row["transaction_type"] == TransactionType.INCOME:
            income = quantize_money(row["total"])
        else:
            expense = quantize_money(row["total"])
    return income, expense


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def analyse_budget(user, budget, *, today: dt.date | None = None) -> BudgetAnalysis:
    """Compute the full analysis for one ``Budget``.

    This is the function every budget endpoint funnels through, so there is
    exactly one implementation of the maths.
    """
    from apps.core.jalali import PERSIAN_MONTHS, month_label

    today = today or dt.date.today()
    start, end = budget.date_range

    progress = month_progress(budget.year, budget.month, today)
    elapsed_percent = Decimal(str(progress["percent_elapsed"]))

    spend_map = spent_by_category(user, start, end)
    actual_income, actual_expense = month_actuals(user, start, end)

    items = list(budget.items.select_related("category", "category__parent"))

    categories: list[CategoryBudgetAnalysis] = []
    total_budgeted = ZERO
    total_spent = ZERO
    essential_total = ZERO
    flexible_total = ZERO

    for item in items:
        category = item.category
        budgeted = quantize_money(item.amount)
        spent, tx_count = spend_map.get(category.pk, (ZERO, 0))
        spent = quantize_money(spent)

        remaining = quantize_money(budgeted - spent)
        consumed = percentage(spent, budgeted)
        pace_state = classify_pace(consumed, elapsed_percent)
        status = classify_status(consumed, spent)

        # Extrapolate to month end from the daily rate so far. Deliberately
        # withheld for a past month (the outcome is already known, so a
        # projection would be noise) and for day 0 (no rate to extrapolate).
        projected: Decimal | None = None
        if progress["days_elapsed"] > 0 and progress["is_current_month"]:
            daily_rate = safe_divide(spent, Decimal(progress["days_elapsed"]))
            projected = quantize_money(daily_rate * Decimal(progress["days_in_month"]))

        categories.append(
            CategoryBudgetAnalysis(
                category_id=category.pk,
                category_name=category.name,
                category_icon=category.icon,
                category_color=category.color,
                category_full_path=category.full_path,
                is_essential=item.is_essential,
                budgeted=budgeted,
                spent=spent,
                remaining=remaining,
                consumed_percent=consumed,
                elapsed_percent=elapsed_percent,
                pace_delta=(consumed - elapsed_percent),
                status=status,
                status_label=STATUS_LABELS[status],
                pace_state=pace_state,
                message=build_message(
                    status, pace_state, spent > 0, consumed, elapsed_percent
                ),
                projected_total=projected,
                projected_over_budget=bool(projected is not None and projected > budgeted),
                transaction_count=tx_count,
                days_elapsed=progress["days_elapsed"],
                days_in_month=progress["days_in_month"],
            )
        )

        total_budgeted += budgeted
        total_spent += spent
        if item.is_essential:
            essential_total += budgeted
        else:
            flexible_total += budgeted

    # Spend on categories that are not in the budget at all. Surfaced so the
    # user can see the whole picture rather than a flattering subset.
    budgeted_ids = {item.category_id for item in items}
    for category_id, (amount, _count) in spend_map.items():
        if category_id not in budgeted_ids:
            total_spent += amount

    # Sort by consumption descending: the categories that need attention
    # first, which is the opposite of the model's amount-descending default.
    categories.sort(key=lambda c: (-c.consumed_percent, -c.spent))

    return BudgetAnalysis(
        budget_id=budget.pk,
        year=budget.year,
        month=budget.month,
        month_name=PERSIAN_MONTHS[budget.month - 1],
        label=budget.label,
        expected_income=quantize_money(budget.expected_income),
        savings_target=quantize_money(budget.savings_target),
        investment_target=quantize_money(budget.investment_target),
        debt_payment_target=quantize_money(budget.debt_payment_target),
        flexible_budget=quantize_money(budget.flexible_budget),
        is_oversubscribed=budget.is_oversubscribed,
        total_budgeted=quantize_money(total_budgeted),
        total_spent=quantize_money(total_spent),
        total_remaining=quantize_money(total_budgeted - total_spent),
        total_consumed_percent=percentage(total_spent, total_budgeted),
        days_elapsed=progress["days_elapsed"],
        days_in_month=progress["days_in_month"],
        days_remaining=max(progress["days_in_month"] - progress["days_elapsed"], 0),
        elapsed_percent=elapsed_percent,
        categories=categories,
        essential_total=quantize_money(essential_total),
        flexible_total=quantize_money(flexible_total),
        actual_income=actual_income,
        actual_expense=actual_expense,
        has_budget=True,
        has_items=bool(items),
    )


def empty_analysis(user, year: int, month: int, *, today: dt.date | None = None) -> BudgetAnalysis:
    """Analysis for a month with no budget yet.

    Returns a well-formed object with zeros rather than an error or a 404, so
    the client can render the month with real actuals and a prompt to set up a
    budget — which is a much better first-run experience than an error page.
    """
    from apps.core.jalali import PERSIAN_MONTHS, month_label

    today = today or dt.date.today()
    progress = month_progress(year, month, today)
    elapsed_percent = Decimal(str(progress["percent_elapsed"]))

    start, end = jalali_month_bounds(year, month)
    actual_income, actual_expense = month_actuals(user, start, end)

    return BudgetAnalysis(
        budget_id=None,
        year=year,
        month=month,
        month_name=PERSIAN_MONTHS[month - 1] if 1 <= month <= 12 else "",
        # Shared with `Budget.label` so a month with a budget and a month
        # without one are labelled identically. They used to differ in digits.
        label=month_label(year, month),
        expected_income=ZERO,
        savings_target=ZERO,
        investment_target=ZERO,
        debt_payment_target=ZERO,
        flexible_budget=ZERO,
        is_oversubscribed=False,
        total_budgeted=ZERO,
        total_spent=quantize_money(actual_expense),
        total_remaining=ZERO,
        total_consumed_percent=ZERO,
        days_elapsed=progress["days_elapsed"],
        days_in_month=progress["days_in_month"],
        days_remaining=max(progress["days_in_month"] - progress["days_elapsed"], 0),
        elapsed_percent=elapsed_percent,
        categories=[],
        actual_income=actual_income,
        actual_expense=actual_expense,
        has_budget=False,
        has_items=False,
    )
