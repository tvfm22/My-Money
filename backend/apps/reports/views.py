"""Report and dashboard aggregation.

Everything here is a read-only projection over the domain models. The reports
endpoint deliberately returns *all* the app's charts in one response: the
reports page is a single screen, and issuing six parallel requests for it would
make the page feel slow on a phone for no benefit.

Chart data is shaped for the client (labels pre-formatted in Persian, values as
strings) so the frontend does no number formatting of its own for money.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db.models import Count, Q, Sum
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.assets.services import (
    asset_growth,
    asset_type_breakdown,
    net_worth,
    net_worth_history,
)
from apps.assets.models import Asset
from apps.budgets.models import Budget
from apps.budgets.services import analyse_budget, empty_analysis, spent_by_category
from apps.categories.models import Category
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
from apps.core.money import percentage, quantize_money, ZERO
from apps.core.permissions import IsOwner
from apps.debts.models import Debt, DebtDirection
from apps.transactions.models import Transaction, TransactionType
from apps.transactions.services import (
    build_buckets,
    spending_type_breakdown,
    spending_type_by_category,
)


def _resolve_month(request) -> tuple[int, int]:
    """Resolve the requested Jalali month, defaulting to the current one."""
    return resolve_month_param(request)


def _change(current: Decimal, previous: Decimal) -> dict:
    """Absolute and percentage change, with Persian display strings.

    A percentage change from zero has no meaningful value, so it is reported as
    None rather than as an infinite or 100% figure that would mislead.
    """
    delta = current - previous
    percent = percentage(delta, previous) if previous > 0 else None

    return {
        "current": str(quantize_money(current)),
        "previous": str(quantize_money(previous)),
        "delta": str(quantize_money(delta)),
        "percent": str(percent) if percent is not None else None,
        "direction": "up" if delta > 0 else ("down" if delta < 0 else "flat"),
        "delta_display": format_money(abs(delta)),
        "percent_display": format_percent(abs(percent)) if percent is not None else None,
    }


# ---------------------------------------------------------------------------
# Individual reports
# ---------------------------------------------------------------------------


def spending_by_category(user, year: int, month: int) -> dict:
    """Donut chart data: expense totals per category for a Jalali month."""
    start, end = jalali_month_bounds(year, month)

    rows = (
        Transaction.objects.for_user(user)
        .filter(
            transaction_type=TransactionType.EXPENSE,
            occurred_on__gte=start,
            occurred_on__lte=end,
        )
        .values("category_id")
        .annotate(total=Sum("amount"), count=Count("id"))
        .order_by("-total")
    )

    total = sum((quantize_money(row["total"]) for row in rows), ZERO)

    categories = {
        c.pk: c
        for c in Category.objects.for_user(user).filter(
            pk__in=[row["category_id"] for row in rows if row["category_id"]]
        ).select_related("parent")
    }

    slices = []
    for row in rows:
        category = categories.get(row["category_id"])
        if category is None:
            continue
        amount = quantize_money(row["total"])
        share = percentage(amount, total)
        slices.append(
            {
                "category_id": category.pk,
                "name": category.full_path,
                "short_name": category.name,
                "icon": category.icon,
                "color": category.color,
                "is_subcategory": category.parent_id is not None,
                "total": str(amount),
                "total_display": format_money(amount),
                "share_percent": str(share),
                "share_display": format_percent(share),
                "transaction_count": row["count"],
            }
        )

    return {
        "total": str(quantize_money(total)),
        "total_display": format_money(total),
        "slices": slices,
        "month": month,
        "year": year,
    }


def monthly_trend(user, *, months: int = 6) -> dict:
    """Income and expense per Jalali month, for the trend chart."""
    year, month = current_jalali_month()
    series = []

    for offset in range(months - 1, -1, -1):
        y, m = add_jalali_months(year, month, -offset)
        start, end = jalali_month_bounds(y, m)

        totals = (
            Transaction.objects.for_user(user)
            .filter(occurred_on__gte=start, occurred_on__lte=end)
            .aggregate(
                income=Sum("amount", filter=Q(transaction_type=TransactionType.INCOME)),
                expense=Sum("amount", filter=Q(transaction_type=TransactionType.EXPENSE)),
            )
        )

        income = quantize_money(totals["income"] or ZERO)
        expense = quantize_money(totals["expense"] or ZERO)

        series.append(
            {
                "year": y,
                "month": m,
                "key": f"{y}-{m:02d}",
                "label": PERSIAN_MONTHS[m - 1],
                "label_short": to_persian_digits(PERSIAN_MONTHS[m - 1][:4]),
                "income": str(income),
                "expense": str(expense),
                "net": str(quantize_money(income - expense)),
            }
        )

    return {"series": series, "months": months}


def budget_vs_actual(user, year: int, month: int) -> dict:
    """Budgeted vs actual spending per category for a Jalali month.

    Each row also carries the essential / flexible / wasted split of that
    category's spending, so the drill-down can answer "where did this category's
    money actually go?" without a second round trip.
    """
    budget = Budget.objects.for_user(user).filter(year=year, month=month).first()

    if budget is None:
        return {
            "has_budget": False,
            "year": year,
            "month": month,
            "rows": [],
            "totals": {
                "budgeted": "0.00",
                "spent": "0.00",
                "budgeted_display": format_money(0),
                "spent_display": format_money(0),
            },
        }

    analysis = analyse_budget(user, budget)

    start, end = jalali_month_bounds(year, month)
    splits = spending_type_by_category(user, start, end)

    def _split_for(item) -> dict:
        """This category's split, already rolled up from its subcategories.

        The roll-up happens inside `spending_type_by_category`, using the same
        rule as `spent_by_category` — so these buckets sum to the `spent` figure
        on the same row rather than to some near-miss of it.
        """
        return splits.get(
            item.category_id,
            {
                "total": "0.00",
                "total_display": format_money(0),
                "buckets": build_buckets({}, ZERO),
            },
        )

    rows = [
        {
            "category_id": item.category_id,
            "name": item.category_name,
            "full_path": item.category_full_path,
            "icon": item.category_icon,
            "color": item.category_color,
            "budgeted": str(item.budgeted),
            "spent": str(item.spent),
            "remaining": str(item.remaining),
            "consumed_percent": str(item.consumed_percent),
            "status": item.status,
            "status_label": item.status_label,
            "budgeted_display": format_money(item.budgeted),
            "spent_display": format_money(item.spent),
            "spending_types": _split_for(item),
        }
        for item in analysis.categories
    ]

    return {
        "has_budget": True,
        "year": year,
        "month": month,
        "rows": rows,
        "totals": {
            "budgeted": str(analysis.total_budgeted),
            "spent": str(analysis.total_spent),
            "remaining": str(analysis.total_remaining),
            "consumed_percent": str(analysis.total_consumed_percent),
            "budgeted_display": format_money(analysis.total_budgeted),
            "spent_display": format_money(analysis.total_spent),
            "remaining_display": format_money(analysis.total_remaining),
        },
    }


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def spending_by_type(user, year: int, month: int) -> dict:
    """Essential / flexible / wasted split of one Jalali month's expenses.

    A thin month-aware wrapper: the split itself lives in the transactions app,
    because the reports page, the dashboard and the budget drill-down all need
    the same numbers and three copies of the same `Sum` is how they drift.
    """
    start, end = jalali_month_bounds(year, month)
    payload = spending_type_breakdown(user, start, end)
    payload["year"] = year
    payload["month"] = month
    return payload


class DashboardView(APIView):
    """Everything the home screen needs, in one request.

    GET /api/dashboard/?month=1405-06

    The home screen must answer "وضعیت مالی من الان چطور است؟" immediately. A
    single request means one loading state instead of five staggered ones.
    """

    permission_classes = [IsOwner]

    def get(self, request):
        user = request.user
        year, month = _resolve_month(request)
        start, end = jalali_month_bounds(year, month)

        # --- This month's actuals --------------------------------------
        totals = (
            Transaction.objects.for_user(user)
            .filter(occurred_on__gte=start, occurred_on__lte=end)
            .aggregate(
                income=Sum("amount", filter=Q(transaction_type=TransactionType.INCOME)),
                expense=Sum("amount", filter=Q(transaction_type=TransactionType.EXPENSE)),
                count=Count("id"),
            )
        )
        income = quantize_money(totals["income"] or ZERO)
        expense = quantize_money(totals["expense"] or ZERO)

        # --- Last month, for comparison ---------------------------------
        prev_year, prev_month = add_jalali_months(year, month, -1)
        prev_start, prev_end = jalali_month_bounds(prev_year, prev_month)

        prev_totals = (
            Transaction.objects.for_user(user)
            .filter(occurred_on__gte=prev_start, occurred_on__lte=prev_end)
            .aggregate(
                income=Sum("amount", filter=Q(transaction_type=TransactionType.INCOME)),
                expense=Sum("amount", filter=Q(transaction_type=TransactionType.EXPENSE)),
            )
        )
        prev_income = quantize_money(prev_totals["income"] or ZERO)
        prev_expense = quantize_money(prev_totals["expense"] or ZERO)

        # --- Account balance --------------------------------------------
        from apps.accounts.views import accounts_with_totals

        accounts = list(accounts_with_totals(user).filter(is_active=True))
        balance = sum(
            (quantize_money(a.current_balance_annotated) for a in accounts), ZERO
        )

        # --- Budget ------------------------------------------------------
        budget = Budget.objects.for_user(user).filter(year=year, month=month).first()
        if budget is not None:
            analysis = analyse_budget(user, budget)
            budget_payload = analysis.to_dict()
        else:
            budget_payload = empty_analysis(user, year, month).to_dict()

        # --- Assets and debts -------------------------------------------
        worth = net_worth(user)

        # --- Spendable: balance minus what is already promised -----------
        # Outstanding debts are money the user has committed but not yet spent,
        # so presenting the raw balance as "spendable" would overstate it.
        payable_remaining = Decimal(worth["total_liabilities"])
        spendable = balance - payable_remaining

        # --- Recent transactions ----------------------------------------
        from apps.transactions.serializers import TransactionSerializer

        recent = list(
            Transaction.objects.for_user(user).with_relations().recent_first()[:8]
        )

        # --- Top budget categories, for the home budget list -------------
        top_categories = budget_payload["categories"][:5]

        progress = month_progress(year, month)

        return Response(
            {
                "greeting_name": user.full_name,
                "month": {
                    "year": year,
                    "month": month,
                    "name": PERSIAN_MONTHS[month - 1],
                    "label": month_label(year, month),
                    "days_elapsed": progress["days_elapsed"],
                    "days_in_month": progress["days_in_month"],
                    "days_remaining": progress["days_in_month"] - progress["days_elapsed"],
                    "elapsed_percent": str(progress["percent_elapsed"]),
                    "elapsed_display": format_percent(progress["percent_elapsed"]),
                },
                "summary": {
                    "balance": str(quantize_money(balance)),
                    "balance_display": format_money(balance),
                    "income": str(income),
                    "income_display": format_money(income),
                    "expense": str(expense),
                    "expense_display": format_money(expense),
                    "net": str(quantize_money(income - expense)),
                    "net_display": format_money(income - expense),
                    "spendable": str(quantize_money(spendable)),
                    "spendable_display": format_money(spendable),
                    "total_assets": worth["total_assets"],
                    "total_assets_display": worth["total_assets_display"],
                    "total_debts": worth["total_liabilities"],
                    "total_debts_display": worth["total_liabilities_display"],
                    "total_receivables": worth["total_receivables"],
                    "total_receivables_display": worth["total_receivables_display"],
                    "net_worth": worth["net_worth"],
                    "net_worth_display": worth["net_worth_display"],
                    "transactions_count": totals["count"],
                },
                "comparison": {
                    # The label belongs beside the comparison it describes. The
                    # client cannot reconstruct which month "previous" means —
                    # the Jalali arithmetic and the month names both live on
                    # this side — and guessing it produced a sentence naming a
                    # month that did not exist in the payload.
                    "previous_month_label": month_label(prev_year, prev_month),
                    "income": _change(income, prev_income),
                    "expense": _change(expense, prev_expense),
                },
                "budget": {
                    "has_budget": budget_payload["has_budget"],
                    "label": budget_payload["label"],
                    "totals": budget_payload["totals"],
                    "plan": budget_payload["plan"],
                    "top_categories": top_categories,
                    "categories_count": len(budget_payload["categories"]),
                },
                # How this month's spending splits by the user's own
                # classification. Flat, not nested under `budget`, because it is
                # about the month's expenses rather than about the plan.
                "spending_types": spending_type_breakdown(user, start, end),
                "recent_transactions": TransactionSerializer(recent, many=True).data,
                "accounts_count": len(accounts),
            }
        )


class ReportsView(APIView):
    """All report series for a month, in one payload.

    GET /api/reports/?month=1405-06&trend_months=6&worth_months=12
    """

    permission_classes = [IsOwner]

    def get(self, request):
        user = request.user
        year, month = _resolve_month(request)

        try:
            trend_months = min(int(request.query_params.get("trend_months", 6)), 24)
        except (TypeError, ValueError):
            trend_months = 6

        try:
            worth_months = min(int(request.query_params.get("worth_months", 12)), 36)
        except (TypeError, ValueError):
            worth_months = 12

        return Response(
            {
                "month": {
                    "year": year,
                    "month": month,
                    "name": PERSIAN_MONTHS[month - 1],
                    "label": month_label(year, month),
                },
                "spending_by_category": spending_by_category(user, year, month),
                "spending_by_type": spending_by_type(user, year, month),
                "monthly_trend": monthly_trend(user, months=trend_months),
                "budget_vs_actual": budget_vs_actual(user, year, month),
                "net_worth_history": {
                    "history": net_worth_history(user, months=worth_months),
                },
                "asset_breakdown": asset_type_breakdown(user),
                "net_worth": net_worth(user),
            }
        )


class SpendingByCategoryView(APIView):
    """Standalone endpoint for the category donut, filterable by date range."""

    permission_classes = [IsOwner]

    def get(self, request):
        year, month = _resolve_month(request)
        return Response(spending_by_category(request.user, year, month))


class MonthlyTrendView(APIView):
    """Standalone income/expense trend."""

    permission_classes = [IsOwner]

    def get(self, request):
        try:
            months = min(int(request.query_params.get("months", 6)), 24)
        except (TypeError, ValueError):
            months = 6
        return Response(monthly_trend(request.user, months=months))


class BudgetVsActualView(APIView):
    """Standalone budget comparison."""

    permission_classes = [IsOwner]

    def get(self, request):
        year, month = _resolve_month(request)
        return Response(budget_vs_actual(request.user, year, month))
