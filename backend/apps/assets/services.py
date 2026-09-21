"""Asset services: value annotation and net-worth calculation."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db.models import DecimalField, OuterRef, Subquery
from django.db.models.functions import Coalesce

from apps.core.jalali import format_money, format_percent
from apps.core.money import percentage, quantize_money

from .models import Asset, AssetType, AssetValuation

MONEY_FIELD = DecimalField(max_digits=18, decimal_places=2)


def annotate_current_value(queryset):
    """Annotate each asset with its latest valuation in a single query.

    Uses a correlated subquery ordered by date descending, so listing N assets
    is two queries total rather than N+1.
    """
    latest_value = (
        AssetValuation.objects.filter(asset=OuterRef("pk"))
        .order_by("-valued_on", "-id")
        .values("value")[:1]
    )

    return queryset.annotate(
        latest_value=Subquery(latest_value, output_field=MONEY_FIELD),
    ).annotate(
        # Fall back to the purchase value when nothing has been valued yet.
        current_value_annotated=Coalesce(
            "latest_value", "purchase_value", output_field=MONEY_FIELD
        ),
    )


def asset_totals(user) -> dict:
    """Totals across a user's assets: current value, purchase value, return."""
    assets = list(
        annotate_current_value(Asset.objects.for_user(user).filter(is_active=True))
    )

    current_total = Decimal("0.00")
    purchase_total = Decimal("0.00")
    included_current = Decimal("0.00")
    by_type: dict[str, Decimal] = {}

    for asset in assets:
        current = quantize_money(asset.current_value_annotated)
        current_total += current
        purchase_total += asset.purchase_value or Decimal("0.00")
        if asset.include_in_net_worth:
            included_current += current

        label = asset.get_asset_type_display()
        by_type[label] = by_type.get(label, Decimal("0.00")) + current

    nominal_return = current_total - purchase_total

    return {
        "current_value": str(quantize_money(current_total)),
        "purchase_value": str(quantize_money(purchase_total)),
        "included_value": str(quantize_money(included_current)),
        "nominal_return": str(quantize_money(nominal_return)),
        "nominal_return_percent": str(percentage(nominal_return, purchase_total)),
        "assets_count": len(assets),
        "current_value_display": format_money(current_total),
        "purchase_value_display": format_money(purchase_total),
        "nominal_return_display": format_money(nominal_return),
        "nominal_return_percent_display": format_percent(
            percentage(nominal_return, purchase_total)
        ),
        "by_type": [
            {
                "type": key,
                "total": str(quantize_money(value)),
                "display": format_money(value),
            }
            for key, value in sorted(by_type.items(), key=lambda kv: -kv[1])
        ],
    }


def net_worth(user, *, as_of: dt.date | None = None) -> dict:
    """Net worth = total assets − total liabilities.

    Liabilities are the outstanding balance of debts the user owes
    (direction='payable'). Receivables are *not* counted as assets here: they
    are money not yet in hand, and counting them would flatter the number.
    They are reported separately so the user can see them.
    """
    from apps.debts.models import Debt, DebtDirection

    as_of = as_of or dt.date.today()

    # --- Assets ---------------------------------------------------------
    assets = list(
        annotate_current_value(
            Asset.objects.for_user(user).filter(is_active=True, include_in_net_worth=True)
        )
    )
    total_assets = sum(
        (quantize_money(a.current_value_annotated) for a in assets), Decimal("0.00")
    )

    # --- Liabilities ----------------------------------------------------
    payable_debts = list(
        Debt.objects.for_user(user)
        .payable()
        .filter(settled_at__isnull=True)
        .prefetch_related("payments")
    )
    total_liabilities = sum(
        (debt.remaining_amount for debt in payable_debts), Decimal("0.00")
    )

    # --- Receivables (reported, not counted) ----------------------------
    receivable_debts = list(
        Debt.objects.for_user(user)
        .receivable()
        .filter(settled_at__isnull=True)
        .prefetch_related("payments")
    )
    total_receivables = sum(
        (debt.remaining_amount for debt in receivable_debts), Decimal("0.00")
    )

    net = total_assets - total_liabilities

    return {
        "as_of": as_of.isoformat(),
        "total_assets": str(quantize_money(total_assets)),
        "total_liabilities": str(quantize_money(total_liabilities)),
        "net_worth": str(quantize_money(net)),
        "total_receivables": str(quantize_money(total_receivables)),
        "total_assets_display": format_money(total_assets),
        "total_liabilities_display": format_money(total_liabilities),
        "net_worth_display": format_money(net),
        "total_receivables_display": format_money(total_receivables),
        "assets_count": len(assets),
        "liabilities_count": len(payable_debts),
        "receivables_count": len(receivable_debts),
        "is_negative": net < 0,
    }


def net_worth_history(user, *, months: int = 12) -> list[dict]:
    """Net worth at the end of each of the last N Jalali months.

    Reconstructed from valuation history and debt payments rather than from
    periodic snapshots, so it works retroactively and needs no background job.

    For each month end:
      *   assets   = the latest valuation on or before that date (per asset)
      *   liability = principal − payments made on or before that date

    Assets purchased after the month end are excluded, so the early months of a
    new user's history correctly show less than today.
    """
    from apps.core.jalali import add_jalali_months, current_jalali_month, jalali_month_bounds, to_persian_digits
    from apps.debts.models import Debt, DebtDirection

    year, month = current_jalali_month()
    history: list[dict] = []

    assets = list(Asset.objects.for_user(user).filter(is_active=True))
    debts = list(Debt.objects.for_user(user).payable())

    for offset in range(months - 1, -1, -1):
        target_year, target_month = add_jalali_months(year, month, -offset)
        _first, month_end = jalali_month_bounds(target_year, target_month)

        # --- Assets at month end ---------------------------------------
        assets_total = Decimal("0.00")
        for asset in assets:
            if asset.purchase_date and asset.purchase_date > month_end:
                continue  # not owned yet

            valuation = (
                asset.valuations.filter(valued_on__lte=month_end)
                .order_by("-valued_on", "-id")
                .first()
            )
            if valuation is not None:
                assets_total += valuation.value
            elif asset.purchase_date and asset.purchase_date <= month_end:
                # No valuation recorded that early; use what was paid.
                assets_total += asset.purchase_value or Decimal("0.00")

        # --- Liabilities at month end ----------------------------------
        liabilities_total = Decimal("0.00")
        for debt in debts:
            if debt.issued_on and debt.issued_on > month_end:
                continue  # did not exist yet

            paid_by_then = sum(
                (
                    payment.amount
                    for payment in debt.payments.all()
                    if payment.paid_on <= month_end
                ),
                Decimal("0.00"),
            )
            outstanding = debt.principal - paid_by_then
            if outstanding > 0:
                liabilities_total += outstanding

        net = assets_total - liabilities_total

        history.append(
            {
                "year": target_year,
                "month": target_month,
                "key": f"{target_year}-{target_month:02d}",
                "label": to_persian_digits(f"{target_month:02d}/{target_year}"),
                "month_name": to_persian_digits(str(target_month)),
                "assets": str(quantize_money(assets_total)),
                "liabilities": str(quantize_money(liabilities_total)),
                "net_worth": str(quantize_money(net)),
            }
        )

    return history


def asset_type_breakdown(user) -> list[dict]:
    """Assets grouped by type with totals and share of the portfolio."""
    assets = list(
        annotate_current_value(
            Asset.objects.for_user(user).filter(is_active=True, include_in_net_worth=True)
        )
    )

    total = sum((quantize_money(a.current_value_annotated) for a in assets), Decimal("0.00"))

    grouped: dict[str, dict] = {}
    for asset in assets:
        key = asset.asset_type
        bucket = grouped.setdefault(
            key,
            {
                "type": key,
                "label": asset.get_asset_type_display(),
                "total": Decimal("0.00"),
                "count": 0,
            },
        )
        bucket["total"] += quantize_money(asset.current_value_annotated)
        bucket["count"] += 1

    result = []
    for bucket in grouped.values():
        share = percentage(bucket["total"], total) if total > 0 else Decimal("0.00")
        result.append(
            {
                "type": bucket["type"],
                "label": bucket["label"],
                "total": str(quantize_money(bucket["total"])),
                "total_display": format_money(bucket["total"]),
                "count": bucket["count"],
                "share_percent": str(share),
                "share_display": format_percent(share),
            }
        )

    result.sort(key=lambda row: -Decimal(row["total"]))
    return result


def asset_growth(user, *, asset_id: int | None = None) -> list[dict]:
    """Valuation history for charting, optionally for a single asset."""
    queryset = AssetValuation.objects.filter(asset__user=user)
    if asset_id:
        queryset = queryset.filter(asset_id=asset_id)

    rows = (
        queryset.order_by("valued_on")
        .values("valued_on", "value", "asset_id", "asset__name")
    )

    return [
        {
            "date": row["valued_on"].isoformat(),
            "value": str(quantize_money(row["value"])),
            "asset_id": row["asset_id"],
            "asset_name": row["asset__name"],
        }
        for row in rows
    ]
