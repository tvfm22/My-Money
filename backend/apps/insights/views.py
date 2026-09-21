"""Financial insights — «بینش مالی».

Hard rule enforced by this module: every insight is computed from transactions,
budgets, debts or assets the user actually recorded. Nothing is inferred,
estimated, or generated. If the data to support a statement is not present, the
statement is not made.

That constraint shapes the whole design:

*   Every insight carries a `metric` dict with the raw numbers behind it, so
    the claim is auditable in the UI ("چرا این را می‌گویید؟").
*   An insight is only emitted when its underlying comparison is well-defined.
    A month-over-month change with no prior-month data is skipped, not shown
    as "0%".
*   Percentages from a zero base are withheld rather than shown as 100%.

Tone rule: informational, never judgmental (product spec section 36). Insights
describe what the numbers show; they do not grade the user.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Count, Q, Sum
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsOwner

from apps.budgets.models import Budget
from apps.budgets.services import analyse_budget, spent_by_category
from apps.categories.models import Category, CategoryKind
from apps.core.jalali import (
    PERSIAN_MONTHS,
    add_jalali_months,
    current_jalali_month,
    format_money,
    format_percent,
    jalali_month_bounds,
    month_progress,
    to_persian_digits,
    resolve_month_param,
    month_label,
)
from apps.core.money import ZERO, percentage, quantize_money
from apps.transactions.models import Transaction, TransactionType

# Insight kinds let the client pick an icon and a colour role without parsing
# the message text.
KIND_TREND_UP = "trend_up"
KIND_TREND_DOWN = "trend_down"
KIND_BUDGET_PACE = "budget_pace"
KIND_BUDGET_LIMIT = "budget_limit"
KIND_TOP_CATEGORY = "top_category"
KIND_MONTH_PROGRESS = "month_progress"
KIND_SAVINGS_RATE = "savings_rate"
KIND_NO_SPEND = "no_spend"
KIND_DEBT_DUE = "debt_due"
KIND_LARGEST_EXPENSE = "largest_expense"
KIND_AVERAGE_DAILY = "average_daily"

# Severity is about how much attention the item deserves, not whether the user
# did something wrong.
SEVERITY_INFO = "info"
SEVERITY_POSITIVE = "positive"
SEVERITY_WARNING = "warning"
SEVERITY_ATTENTION = "attention"

# How far a category must move month-over-month before it is worth reporting.
# Below this, the change is noise and would just add clutter.
TREND_THRESHOLD_PERCENT = Decimal("10")


@dataclass
class Insight:
    """A single data-backed observation."""

    kind: str
    severity: str
    title: str
    message: str
    icon: str = "info"
    # The raw numbers behind the claim, so the UI can show its work.
    metric: dict = field(default_factory=dict)
    # Optional navigation target, so tapping an insight goes somewhere useful.
    action: dict | None = None

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "severity": self.severity,
            "title": self.title,
            "message": self.message,
            "icon": self.icon,
            "metric": self.metric,
            "action": self.action,
        }


def _month_label(year: int, month: int) -> str:
    """Kept as a thin alias so the insight copy reads naturally."""
    return month_label(year, month)


def _month_totals(user, year: int, month: int) -> tuple[Decimal, Decimal]:
    """(income, expense) actually recorded in a Jalali month."""
    start, end = jalali_month_bounds(year, month)
    totals = (
        Transaction.objects.for_user(user)
        .filter(occurred_on__gte=start, occurred_on__lte=end)
        .aggregate(
            income=Sum("amount", filter=Q(transaction_type=TransactionType.INCOME)),
            expense=Sum("amount", filter=Q(transaction_type=TransactionType.EXPENSE)),
        )
    )
    return quantize_money(totals["income"] or ZERO), quantize_money(totals["expense"] or ZERO)


def _category_totals(user, year: int, month: int) -> dict[int, Decimal]:
    """Expense per top-level category in a month, children rolled into parents."""
    start, end = jalali_month_bounds(year, month)

    rows = (
        Transaction.objects.for_user(user)
        .filter(
            transaction_type=TransactionType.EXPENSE,
            occurred_on__gte=start,
            occurred_on__lte=end,
        )
        .values("category_id", "category__parent_id")
        .annotate(total=Sum("amount"))
    )

    rolled: dict[int, Decimal] = {}
    for row in rows:
        category_id = row["category_id"]
        if category_id is None:
            continue
        amount = quantize_money(row["total"])
        parent_id = row["category__parent_id"]

        # Roll subcategory spending into the parent, so a comparison is made at
        # a consistent level of granularity across both months.
        key = parent_id if parent_id else category_id
        rolled[key] = rolled.get(key, ZERO) + amount

    return rolled


def generate_insights(user, *, year: int | None = None, month: int | None = None) -> list[Insight]:
    """Build the insight list for a month, most useful first.

    Ordering rationale: a limit being hit matters more than a trend, which
    matters more than a neutral observation about the calendar. Items are
    sorted by severity, then by the order they were generated within a severity.
    """
    # Resolve the month: default to the current Jalali month when not supplied.
    # Written as an explicit branch rather than `year or current_jalali_month()`
    # because that expression returns a *tuple* for a falsy year, which is not
    # what the unpacking below expects.
    if year is None or month is None:
        current_year, current_month = current_jalali_month()
        year = year if year is not None else current_year
        month = month if month is not None else current_month

    today = dt.date.today()

    insights: list[Insight] = []

    progress = month_progress(year, month, today)
    elapsed_percent = Decimal(str(progress["percent_elapsed"]))

    income, expense = _month_totals(user, year, month)

    prev_year, prev_month = add_jalali_months(year, month, -1)
    prev_income, prev_expense = _month_totals(user, prev_year, prev_month)

    # ==================================================================
    # 1. Budget pace and limits
    # ==================================================================
    budget = Budget.objects.for_user(user).filter(year=year, month=month).first()

    if budget is not None:
        analysis = analyse_budget(user, budget, today=today)

        if analysis.has_items:
            insights.append(
                Insight(
                    kind=KIND_MONTH_PROGRESS,
                    severity=SEVERITY_INFO,
                    title="روند ماه",
                    icon="calendar",
                    message=(
                        f"تا امروز {to_persian_digits(str(progress['days_elapsed']))} روز از "
                        f"{to_persian_digits(str(progress['days_in_month']))} روز این ماه گذشته "
                        f"({format_percent(elapsed_percent)}) و "
                        f"{format_percent(analysis.total_consumed_percent)} از بودجه مصرف شده است."
                    ),
                    metric={
                        "days_elapsed": progress["days_elapsed"],
                        "days_in_month": progress["days_in_month"],
                        "elapsed_percent": str(elapsed_percent),
                        "budget_consumed_percent": str(analysis.total_consumed_percent),
                        "budgeted": str(analysis.total_budgeted),
                        "spent": str(analysis.total_spent),
                    },
                    action={"type": "budget", "year": year, "month": month},
                )
            )

            # Over-budget categories: the most actionable thing we can say.
            over = [c for c in analysis.categories if c.status == "over"]
            for item in over[:2]:
                insights.append(
                    Insight(
                        kind=KIND_BUDGET_LIMIT,
                        severity=SEVERITY_ATTENTION,
                        title=f"بودجه {item.category_name} تمام شده",
                        message=(
                            f"در دسته «{item.category_name}» "
                            f"{format_money(item.spent)} از {format_money(item.budgeted)} "
                            f"خرج شده است ({item.to_dict()['consumed_display']} بودجه)."
                        ),
                        icon=item.category_icon,
                        metric={
                            "category_id": item.category_id,
                            "budgeted": str(item.budgeted),
                            "spent": str(item.spent),
                            "over_by": item.to_dict()["over_budget_amount"],
                            "consumed_percent": str(item.consumed_percent),
                        },
                        action={
                            "type": "budget_category",
                            "category_id": item.category_id,
                            "year": year,
                            "month": month,
                        },
                    )
                )

            # Near the limit.
            near = [c for c in analysis.categories if c.status == "near_limit"]
            for item in near[:2]:
                insights.append(
                    Insight(
                        kind=KIND_BUDGET_LIMIT,
                        severity=SEVERITY_WARNING,
                        title=f"نزدیک به سقف بودجه {item.category_name}",
                        message=(
                            f"{item.to_dict()['consumed_display']} از بودجه «{item.category_name}» "
                            f"مصرف شده و {format_money(item.remaining)} باقی مانده است."
                        ),
                        icon=item.category_icon,
                        metric={
                            "category_id": item.category_id,
                            "budgeted": str(item.budgeted),
                            "spent": str(item.spent),
                            "remaining": str(item.remaining),
                            "consumed_percent": str(item.consumed_percent),
                        },
                        action={
                            "type": "budget_category",
                            "category_id": item.category_id,
                            "year": year,
                            "month": month,
                        },
                    )
                )

            # Ahead of pace. The spec's example: "توجه — سرعت مصرف این بودجه
            # بیشتر از روند ماهانه است."
            ahead = [
                c
                for c in analysis.categories
                if c.pace_state == "ahead" and c.status not in ("over", "near_limit")
            ]
            for item in ahead[:2]:
                insights.append(
                    Insight(
                        kind=KIND_BUDGET_PACE,
                        severity=SEVERITY_WARNING,
                        title=f"سرعت مصرف {item.category_name}",
                        message=(
                            f"سرعت مصرف «{item.category_name}» بیشتر از روند ماهانه است: "
                            f"{item.to_dict()['consumed_display']} بودجه مصرف شده در حالی که "
                            f"{format_percent(elapsed_percent)} از ماه گذشته است."
                        ),
                        icon="trending-up",
                        metric={
                            "category_id": item.category_id,
                            "consumed_percent": str(item.consumed_percent),
                            "elapsed_percent": str(elapsed_percent),
                            "pace_delta": str(item.pace_delta),
                            "projected_total": (
                                str(item.projected_total)
                                if item.projected_total is not None
                                else None
                            ),
                            "budgeted": str(item.budgeted),
                        },
                        action={
                            "type": "budget_category",
                            "category_id": item.category_id,
                            "year": year,
                            "month": month,
                        },
                    )
                )

            # Clearly behind pace — reported as positive without being
            # congratulatory, which would read as patronizing.
            behind = [
                c
                for c in analysis.categories
                if c.pace_state == "behind" and c.spent > 0 and c.pace_delta < Decimal("-25")
            ]
            for item in behind[:1]:
                insights.append(
                    Insight(
                        kind=KIND_BUDGET_PACE,
                        severity=SEVERITY_POSITIVE,
                        title=f"مصرف {item.category_name} کمتر از روند ماه",
                        message=(
                            f"در «{item.category_name}» {item.to_dict()['consumed_display']} از بودجه "
                            f"مصرف شده، در حالی که {format_percent(elapsed_percent)} از ماه گذشته است."
                        ),
                        icon="trending-down",
                        metric={
                            "category_id": item.category_id,
                            "consumed_percent": str(item.consumed_percent),
                            "elapsed_percent": str(elapsed_percent),
                            "remaining": str(item.remaining),
                        },
                    )
                )

    # ==================================================================
    # 2. Month-over-month category trends
    # ==================================================================
    if prev_expense > 0:
        current_categories = _category_totals(user, year, month)
        previous_categories = _category_totals(user, prev_year, prev_month)

        categories = {
            c.pk: c
            for c in Category.objects.for_user(user).filter(
                pk__in=set(current_categories) | set(previous_categories)
            )
        }

        changes = []
        for category_id, current_amount in current_categories.items():
            previous_amount = previous_categories.get(category_id, ZERO)
            # A change from zero has no meaningful percentage.
            if previous_amount <= 0:
                continue
            change = percentage(current_amount - previous_amount, previous_amount)
            if abs(change) >= TREND_THRESHOLD_PERCENT:
                changes.append((category_id, current_amount, previous_amount, change))

        changes.sort(key=lambda row: -abs(row[3]))

        for category_id, current_amount, previous_amount, change in changes[:2]:
            category = categories.get(category_id)
            if category is None:
                continue

            if change > 0:
                insights.append(
                    Insight(
                        kind=KIND_TREND_UP,
                        severity=SEVERITY_WARNING,
                        title=f"افزایش هزینه {category.name}",
                        message=(
                            f"هزینه «{category.name}» در {_month_label(year, month)} "
                            f"{format_percent(abs(change))} بیشتر از {_month_label(prev_year, prev_month)} "
                            f"بوده است ({format_money(previous_amount)} → {format_money(current_amount)})."
                        ),
                        icon=category.icon,
                        metric={
                            "category_id": category_id,
                            "current": str(current_amount),
                            "previous": str(previous_amount),
                            "change_percent": str(change),
                        },
                        action={"type": "transactions", "category_id": category_id},
                    )
                )
            else:
                insights.append(
                    Insight(
                        kind=KIND_TREND_DOWN,
                        severity=SEVERITY_POSITIVE,
                        title=f"کاهش هزینه {category.name}",
                        message=(
                            f"هزینه «{category.name}» در {_month_label(year, month)} "
                            f"{format_percent(abs(change))} کمتر از {_month_label(prev_year, prev_month)} "
                            f"بوده است ({format_money(previous_amount)} → {format_money(current_amount)})."
                        ),
                        icon=category.icon,
                        metric={
                            "category_id": category_id,
                            "current": str(current_amount),
                            "previous": str(previous_amount),
                            "change_percent": str(change),
                        },
                    )
                )

    # ==================================================================
    # 3. Largest spending category
    # ==================================================================
    current_categories = _category_totals(user, year, month)
    if current_categories and expense > 0:
        top_id, top_amount = max(current_categories.items(), key=lambda kv: kv[1])
        top_category = Category.objects.for_user(user).filter(pk=top_id).first()
        if top_category is not None:
            share = percentage(top_amount, expense)
            insights.append(
                Insight(
                    kind=KIND_TOP_CATEGORY,
                    severity=SEVERITY_INFO,
                    title="بیشترین هزینه این ماه",
                    message=(
                        f"بیشترین هزینه این ماه مربوط به «{top_category.name}» بوده است: "
                        f"{format_money(top_amount)} که {format_percent(share)} از کل هزینه‌های "
                        f"این ماه است."
                    ),
                    icon=top_category.icon,
                    metric={
                        "category_id": top_id,
                        "amount": str(top_amount),
                        "share_percent": str(share),
                        "total_expense": str(expense),
                    },
                    action={"type": "transactions", "category_id": top_id},
                )
            )

    # ==================================================================
    # 4. Savings rate — only when there is recorded income to reason about
    # ==================================================================
    if income > 0:
        saved = income - expense
        rate = percentage(saved, income)
        if saved > 0:
            insights.append(
                Insight(
                    kind=KIND_SAVINGS_RATE,
                    severity=SEVERITY_POSITIVE,
                    title="اختلاف درآمد و هزینه",
                    message=(
                        f"در {_month_label(year, month)} درآمد شما "
                        f"{format_money(income)} و هزینه‌ها {format_money(expense)} بوده است. "
                        f"اختلاف مثبت: {format_money(saved)} ({format_percent(rate)} از درآمد)."
                    ),
                    icon="piggy-bank",
                    metric={
                        "income": str(income),
                        "expense": str(expense),
                        "saved": str(saved),
                        "savings_rate": str(rate),
                    },
                )
            )
        else:
            insights.append(
                Insight(
                    kind=KIND_SAVINGS_RATE,
                    severity=SEVERITY_WARNING,
                    title="هزینه بیش از درآمد ثبت‌شده",
                    message=(
                        f"در {_month_label(year, month)} هزینه‌ها ({format_money(expense)}) "
                        f"از درآمد ثبت‌شده ({format_money(income)}) بیشتر بوده است."
                    ),
                    icon="alert-circle",
                    metric={
                        "income": str(income),
                        "expense": str(expense),
                        "difference": str(quantize_money(expense - income)),
                    },
                )
            )
    elif expense > 0:
        # Spending recorded, no income recorded. Report the fact without
        # implying the user earned nothing — income may simply be unrecorded.
        insights.append(
            Insight(
                kind=KIND_SAVINGS_RATE,
                severity=SEVERITY_INFO,
                title="درآمدی برای این ماه ثبت نشده",
                message=(
                    f"در {_month_label(year, month)} {format_money(expense)} هزینه ثبت شده "
                    "اما درآمدی ثبت نشده است. برای تحلیل کامل‌تر، درآمد این ماه را هم ثبت کنید."
                ),
                icon="wallet",
                metric={"expense": str(expense), "income": "0.00"},
            )
        )

    # ==================================================================
    # 5. Daily average — useful for deciding whether the rest of the month works
    # ==================================================================
    if expense > 0 and progress["days_elapsed"] > 0:
        average_daily = quantize_money(expense / Decimal(progress["days_elapsed"]))
        insights.append(
            Insight(
                kind=KIND_AVERAGE_DAILY,
                severity=SEVERITY_INFO,
                title="میانگین هزینه روزانه",
                message=(
                    f"به‌طور میانگین روزانه {format_money(average_daily)} هزینه ثبت کرده‌اید "
                    f"({format_money(expense)} در {to_persian_digits(str(progress['days_elapsed']))} روز)."
                ),
                icon="activity",
                metric={
                    "average_daily": str(average_daily),
                    "total": str(expense),
                    "days_elapsed": progress["days_elapsed"],
                },
            )
        )

    # ==================================================================
    # 6. Debts nearing or past due
    # ==================================================================
    from apps.debts.models import Debt

    overdue = [
        debt
        for debt in Debt.objects.for_user(user)
        .filter(settled_at__isnull=True, due_on__isnull=False, due_on__lt=today)
        .prefetch_related("payments")
    ]

    if overdue:
        total_overdue = sum((d.remaining_amount for d in overdue), ZERO)
        insights.append(
            Insight(
                kind=KIND_DEBT_DUE,
                severity=SEVERITY_ATTENTION,
                title="بدهی سررسید گذشته",
                message=(
                    f"{to_persian_digits(str(len(overdue)))} مورد بدهی از سررسید گذشته است. "
                    f"مجموع باقی‌مانده: {format_money(total_overdue)}."
                ),
                icon="alert-triangle",
                metric={
                    "count": len(overdue),
                    "total": str(quantize_money(total_overdue)),
                },
                action={"type": "debts", "filter": "overdue"},
            )
        )

    due_soon = [
        debt
        for debt in Debt.objects.for_user(user)
        .filter(
            settled_at__isnull=True,
            due_on__isnull=False,
            due_on__gte=today,
            due_on__lte=today + dt.timedelta(days=7),
        )
        .prefetch_related("payments")
    ]

    if due_soon:
        total_soon = sum((d.remaining_amount for d in due_soon), ZERO)
        insights.append(
            Insight(
                kind=KIND_DEBT_DUE,
                severity=SEVERITY_WARNING,
                title="بدهی نزدیک به سررسید",
                message=(
                    f"{to_persian_digits(str(len(due_soon)))} مورد بدهی در هفت روز آینده سررسید "
                    f"می‌شود. مجموع باقی‌مانده: {format_money(total_soon)}."
                ),
                icon="clock",
                metric={
                    "count": len(due_soon),
                    "total": str(quantize_money(total_soon)),
                },
                action={"type": "debts", "filter": "upcoming"},
            )
        )

    # Order by severity so the most important items lead.
    severity_order = {
        SEVERITY_ATTENTION: 0,
        SEVERITY_WARNING: 1,
        SEVERITY_POSITIVE: 2,
        SEVERITY_INFO: 3,
    }
    insights.sort(key=lambda item: severity_order.get(item.severity, 9))

    return insights


class InsightsView(APIView):
    """GET /api/insights/?month=1405-06"""

    permission_classes = [IsOwner]

    def get(self, request):
        year, month = _resolve_month(request)
        insights = generate_insights(request.user, year=year, month=month)

        return Response(
            {
                "month": {
                    "year": year,
                    "month": month,
                    "name": PERSIAN_MONTHS[month - 1],
                    "label": _month_label(year, month),
                },
                "insights": [insight.to_dict() for insight in insights],
                "count": len(insights),
            }
        )


def _resolve_month(request) -> tuple[int, int]:
    """Resolve the requested Jalali month, defaulting to the current one."""
    return resolve_month_param(request)
