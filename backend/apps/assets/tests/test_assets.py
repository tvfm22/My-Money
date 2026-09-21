"""Asset and net-worth calculation tests.

Net worth is the single number most likely to be quietly wrong, because it
depends on three separate derived things lining up: the latest valuation per
asset, the outstanding balance per payable debt, and the deliberate exclusion
of receivables. These tests pin each of those down.

Money leaves these services as quantized decimal strings (e.g. ``"12000000.00"``)
rather than floats, so the client never re-derives money from a JSON number.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.test import TestCase

from apps.assets.models import Asset, AssetType, AssetValuation
from apps.assets.services import (
    annotate_current_value,
    asset_growth,
    asset_totals,
    asset_type_breakdown,
    net_worth,
    net_worth_history,
)
from apps.debts.models import Debt, DebtDirection, DebtPayment
from apps.users.models import User


class CurrentValueTests(TestCase):
    """``current_value`` must come from the newest valuation, not the last one written."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="asset@test.ir", password="StrongPass!234"
        )
        self.today = dt.date.today()
        self.asset = Asset.objects.create(
            user=self.user,
            name="صندوق طلا",
            asset_type=AssetType.GOLD_FUND,
            purchase_value=Decimal("120000000"),
            purchase_date=self.today - dt.timedelta(days=400),
        )

    def test_falls_back_to_purchase_value_without_valuations(self):
        self.assertEqual(self.asset.current_value, Decimal("120000000"))

    def test_uses_latest_valuation(self):
        AssetValuation.objects.create(
            asset=self.asset,
            value=Decimal("130000000"),
            valued_on=self.today - dt.timedelta(days=60),
        )
        AssetValuation.objects.create(
            asset=self.asset,
            value=Decimal("150000000"),
            valued_on=self.today - dt.timedelta(days=5),
        )
        self.assertEqual(self.asset.current_value, Decimal("150000000"))

    def test_valuation_order_is_by_date_not_insertion_order(self):
        """Inserting an older valuation later must not become the current value."""
        AssetValuation.objects.create(
            asset=self.asset,
            value=Decimal("150000000"),
            valued_on=self.today - dt.timedelta(days=5),
        )
        # Inserted second, but dated earlier.
        AssetValuation.objects.create(
            asset=self.asset,
            value=Decimal("90000000"),
            valued_on=self.today - dt.timedelta(days=90),
        )
        self.assertEqual(self.asset.current_value, Decimal("150000000"))

    def test_valuation_history_is_preserved(self):
        """Updating a value must add history, never overwrite it."""
        for offset, value in [(60, "125000000"), (30, "140000000"), (2, "150000000")]:
            AssetValuation.objects.create(
                asset=self.asset,
                value=Decimal(value),
                valued_on=self.today - dt.timedelta(days=offset),
            )
        self.assertEqual(AssetValuation.objects.filter(asset=self.asset).count(), 3)
        self.assertTrue(self.asset.has_history)

    def test_nominal_return_is_current_minus_purchase(self):
        AssetValuation.objects.create(
            asset=self.asset,
            value=Decimal("150000000"),
            valued_on=self.today,
        )
        self.assertEqual(self.asset.nominal_return, Decimal("30000000"))
        self.assertTrue(self.asset.is_profitable)

    def test_nominal_return_percent_is_exact(self):
        AssetValuation.objects.create(
            asset=self.asset,
            value=Decimal("150000000"),
            valued_on=self.today,
        )
        # 30_000_000 / 120_000_000 == 25%
        self.assertEqual(self.asset.nominal_return_percent, Decimal("25.00"))

    def test_loss_is_reported_as_negative_return(self):
        AssetValuation.objects.create(
            asset=self.asset,
            value=Decimal("90000000"),
            valued_on=self.today,
        )
        self.assertEqual(self.asset.nominal_return, Decimal("-30000000"))
        self.assertFalse(self.asset.is_profitable)

    def test_zero_purchase_value_does_not_divide_by_zero(self):
        free = Asset.objects.create(
            user=self.user,
            name="هدیه",
            asset_type=AssetType.OTHER,
            purchase_value=Decimal("0"),
            purchase_date=self.today,
        )
        AssetValuation.objects.create(
            asset=free, value=Decimal("1000000"), valued_on=self.today
        )
        # Must not raise; the percentage is undefined so it is reported as 0.
        self.assertEqual(free.nominal_return_percent, Decimal("0"))


class AnnotatedValueTests(TestCase):
    """The queryset annotation must agree with the per-object property."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="annot@test.ir", password="StrongPass!234"
        )
        self.today = dt.date.today()
        self.a = Asset.objects.create(
            user=self.user,
            name="طلا",
            asset_type=AssetType.GOLD,
            purchase_value=Decimal("10000000"),
            purchase_date=self.today,
        )
        self.b = Asset.objects.create(
            user=self.user,
            name="سهام",
            asset_type=AssetType.STOCKS,
            purchase_value=Decimal("20000000"),
            purchase_date=self.today,
        )
        AssetValuation.objects.create(
            asset=self.a, value=Decimal("12000000"), valued_on=self.today
        )
        AssetValuation.objects.create(
            asset=self.b, value=Decimal("18000000"), valued_on=self.today
        )

    def test_annotation_matches_property(self):
        annotated = {a.pk: a for a in annotate_current_value(Asset.objects.all())}
        for pk, asset in annotated.items():
            plain = Asset.objects.get(pk=pk)
            self.assertEqual(
                asset.current_value_annotated,
                plain.current_value,
                f"annotation disagrees with property for asset {pk}",
            )

    def test_annotation_avoids_extra_queries(self):
        """Accessing the annotated value must not hit the database again."""
        assets = list(annotate_current_value(Asset.objects.all()))
        with self.assertNumQueries(0):
            for asset in assets:
                _ = asset.current_value_annotated

    def test_annotation_falls_back_to_purchase_value(self):
        c = Asset.objects.create(
            user=self.user,
            name="خودرو",
            asset_type=AssetType.VEHICLE,
            purchase_value=Decimal("500000000"),
            purchase_date=self.today,
        )
        annotated = annotate_current_value(Asset.objects.filter(pk=c.pk)).get()
        self.assertEqual(annotated.current_value_annotated, Decimal("500000000"))


class AssetTotalsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="atotals@test.ir", password="StrongPass!234"
        )
        self.today = dt.date.today()

    def _asset(self, name, kind, purchase, current=None, include=True):
        asset = Asset.objects.create(
            user=self.user,
            name=name,
            asset_type=kind,
            purchase_value=Decimal(purchase),
            purchase_date=self.today - dt.timedelta(days=100),
            include_in_net_worth=include,
        )
        if current is not None:
            AssetValuation.objects.create(
                asset=asset, value=Decimal(current), valued_on=self.today
            )
        return asset

    def test_totals_sum_current_values(self):
        self._asset("طلا", AssetType.GOLD, "10000000", "12000000")
        self._asset("سهام", AssetType.STOCKS, "20000000", "18000000")

        totals = asset_totals(self.user)
        self.assertEqual(totals["current_value"], "30000000.00")
        self.assertEqual(totals["purchase_value"], "30000000.00")
        self.assertEqual(totals["assets_count"], 2)

    def test_nominal_return_totals_across_assets(self):
        self._asset("طلا", AssetType.GOLD, "10000000", "12000000")  # +2M
        self._asset("سهام", AssetType.STOCKS, "20000000", "17000000")  # -3M

        totals = asset_totals(self.user)
        self.assertEqual(totals["nominal_return"], "-1000000.00")

    def test_included_value_excludes_flagged_assets(self):
        self._asset("طلا", AssetType.GOLD, "10000000", "12000000")
        self._asset("قدیمی", AssetType.OTHER, "5000000", "5000000", include=False)

        totals = asset_totals(self.user)
        # Both are counted in the portfolio figure...
        self.assertEqual(totals["current_value"], "17000000.00")
        # ...but only the flagged-in one counts toward net worth.
        self.assertEqual(totals["included_value"], "12000000.00")

    def test_inactive_assets_are_excluded(self):
        self._asset("طلا", AssetType.GOLD, "10000000", "12000000")
        self._asset("فروخته‌شده", AssetType.STOCKS, "20000000", "21000000")
        Asset.objects.filter(user=self.user, name="فروخته‌شده").update(is_active=False)

        totals = asset_totals(self.user)
        self.assertEqual(totals["current_value"], "12000000.00")
        self.assertEqual(totals["assets_count"], 1)

    def test_by_type_groups_and_sorts_descending(self):
        self._asset("طلا۱", AssetType.GOLD, "10000000", "10000000")
        self._asset("طلا۲", AssetType.GOLD, "5000000", "5000000")
        self._asset("سهام", AssetType.STOCKS, "20000000", "40000000")

        totals = asset_totals(self.user)
        by_type = {row["type"]: row for row in totals["by_type"]}
        self.assertEqual(by_type["سهام"]["total"], "40000000.00")
        self.assertEqual(by_type["طلا"]["total"], "15000000.00")
        # Largest first.
        self.assertEqual(totals["by_type"][0]["type"], "سهام")

    def test_display_strings_use_persian_separator(self):
        self._asset("طلا", AssetType.GOLD, "10000000", "12000000")
        totals = asset_totals(self.user)
        self.assertIn("\u066c", totals["current_value_display"])


class NetWorthTests(TestCase):
    """net worth = assets − outstanding payables. Receivables are not assets."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="nw@test.ir", password="StrongPass!234"
        )
        self.today = dt.date.today()

    def _asset(self, current):
        asset = Asset.objects.create(
            user=self.user,
            name="دارایی",
            asset_type=AssetType.DEPOSIT,
            purchase_value=Decimal(current),
            purchase_date=self.today - dt.timedelta(days=100),
        )
        AssetValuation.objects.create(
            asset=asset, value=Decimal(current), valued_on=self.today
        )
        return asset

    def _debt(self, direction, principal, paid=0):
        debt = Debt.objects.create(
            user=self.user,
            direction=direction,
            counterparty="طرف",
            principal=Decimal(principal),
            issued_on=self.today - dt.timedelta(days=90),
            due_on=self.today + dt.timedelta(days=90),
        )
        if paid:
            DebtPayment.objects.create(
                debt=debt, amount=Decimal(paid), paid_on=self.today
            )
        return debt

    def test_net_worth_is_assets_minus_payables(self):
        self._asset("100000000")
        self._debt(DebtDirection.PAYABLE, "30000000")

        data = net_worth(self.user)
        self.assertEqual(data["total_assets"], "100000000.00")
        self.assertEqual(data["total_liabilities"], "30000000.00")
        self.assertEqual(data["net_worth"], "70000000.00")

    def test_receivables_are_reported_but_not_counted_as_assets(self):
        self._asset("100000000")
        self._debt(DebtDirection.RECEIVABLE, "25000000")

        data = net_worth(self.user)
        # A promise to be repaid is not money you hold.
        self.assertEqual(data["total_assets"], "100000000.00")
        self.assertEqual(data["net_worth"], "100000000.00")
        self.assertEqual(data["total_receivables"], "25000000.00")
        self.assertEqual(data["receivables_count"], 1)

    def test_partially_repaid_debt_only_counts_the_remainder(self):
        self._asset("100000000")
        self._debt(DebtDirection.PAYABLE, "40000000", paid="15000000")

        data = net_worth(self.user)
        self.assertEqual(data["total_liabilities"], "25000000.00")
        self.assertEqual(data["net_worth"], "75000000.00")

    def test_settled_debt_contributes_nothing(self):
        self._asset("100000000")
        self._debt(DebtDirection.PAYABLE, "40000000", paid="40000000")

        data = net_worth(self.user)
        self.assertEqual(data["total_liabilities"], "0.00")
        self.assertEqual(data["net_worth"], "100000000.00")

    def test_net_worth_can_be_negative(self):
        self._asset("10000000")
        self._debt(DebtDirection.PAYABLE, "60000000")

        data = net_worth(self.user)
        self.assertEqual(data["net_worth"], "-50000000.00")
        self.assertTrue(data["is_negative"])

    def test_no_assets_means_zero_not_an_error(self):
        data = net_worth(self.user)
        self.assertEqual(data["total_assets"], "0.00")
        self.assertEqual(data["net_worth"], "0.00")
        self.assertFalse(data["is_negative"])

    def test_isolation_between_users(self):
        self._asset("100000000")
        other = User.objects.create_user(
            email="other-nw@test.ir", password="StrongPass!234"
        )
        other_data = net_worth(other)
        self.assertEqual(other_data["total_assets"], "0.00")
        self.assertEqual(other_data["net_worth"], "0.00")


class NetWorthHistoryTests(TestCase):
    """Reconstructing past net worth from valuation history."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="hist@test.ir", password="StrongPass!234"
        )
        self.today = dt.date.today()

    def _asset(self, purchase_value, purchase_days_ago=300, name="طلا"):
        return Asset.objects.create(
            user=self.user,
            name=name,
            asset_type=AssetType.GOLD,
            purchase_value=Decimal(purchase_value),
            purchase_date=self.today - dt.timedelta(days=purchase_days_ago),
        )

    def test_history_has_requested_number_of_points(self):
        asset = self._asset("10000000")
        for offset in range(0, 200, 30):
            AssetValuation.objects.create(
                asset=asset,
                value=Decimal("10000000") + Decimal(offset * 100_000),
                valued_on=self.today - dt.timedelta(days=offset),
            )
        points = net_worth_history(self.user, months=6)
        self.assertEqual(len(points), 6)

    def test_history_points_are_chronological(self):
        asset = self._asset("10000000")
        AssetValuation.objects.create(
            asset=asset, value=Decimal("12000000"), valued_on=self.today
        )
        points = net_worth_history(self.user, months=6)
        keys = [(p["year"], p["month"]) for p in points]
        self.assertEqual(keys, sorted(keys))

    def test_each_point_carries_a_jalali_label(self):
        asset = self._asset("10000000")
        AssetValuation.objects.create(
            asset=asset, value=Decimal("12000000"), valued_on=self.today
        )
        points = net_worth_history(self.user, months=6)
        for point in points:
            # Labels are Persian digits, never Gregorian.
            self.assertNotIn("2026", point["label"])
            self.assertIn("/", point["label"])

    def test_later_valuation_raises_historical_net_worth(self):
        asset = self._asset("10000000", purchase_days_ago=400)
        AssetValuation.objects.create(
            asset=asset,
            value=Decimal("11000000"),
            valued_on=self.today - dt.timedelta(days=150),
        )
        AssetValuation.objects.create(
            asset=asset, value=Decimal("20000000"), valued_on=self.today
        )
        points = net_worth_history(self.user, months=6)
        self.assertLess(
            Decimal(points[0]["net_worth"]),
            Decimal(points[-1]["net_worth"]),
        )

    def test_asset_purchased_later_is_absent_from_earlier_months(self):
        """A recently bought asset must not appear in months before purchase."""
        self._asset("500000000", purchase_days_ago=5, name="خودروی نو")
        points = net_worth_history(self.user, months=6)
        # The oldest month predates the purchase, so net worth is zero there.
        self.assertEqual(Decimal(points[0]["net_worth"]), Decimal("0"))

    def test_history_is_zero_filled_for_a_user_with_no_assets(self):
        points = net_worth_history(self.user, months=6)
        self.assertEqual(len(points), 6)
        self.assertTrue(all(Decimal(p["net_worth"]) == 0 for p in points))

    def test_liabilities_reduce_historical_net_worth(self):
        self._asset("100000000", purchase_days_ago=300)
        debt = Debt.objects.create(
            user=self.user,
            direction=DebtDirection.PAYABLE,
            counterparty="بانک",
            principal=Decimal("40000000"),
            issued_on=self.today - dt.timedelta(days=200),
            due_on=self.today + dt.timedelta(days=200),
        )
        points = net_worth_history(self.user, months=6)
        # The most recent point must net the debt off the asset.
        latest = points[-1]
        self.assertEqual(
            Decimal(latest["net_worth"]),
            Decimal(latest["assets"]) - Decimal(latest["liabilities"]),
        )
        self.assertGreater(Decimal(latest["liabilities"]), Decimal("0"))
        self.assertEqual(debt.remaining_amount, Decimal("40000000"))


class AssetBreakdownTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="break@test.ir", password="StrongPass!234"
        )
        self.today = dt.date.today()

    def _asset(self, kind, current, include=True):
        asset = Asset.objects.create(
            user=self.user,
            name=f"{kind}-{current}",
            asset_type=kind,
            purchase_value=Decimal(current),
            purchase_date=self.today,
            include_in_net_worth=include,
        )
        AssetValuation.objects.create(
            asset=asset, value=Decimal(current), valued_on=self.today
        )
        return asset

    def test_breakdown_groups_by_type(self):
        self._asset(AssetType.GOLD, "10000000")
        self._asset(AssetType.GOLD, "5000000")
        self._asset(AssetType.STOCKS, "20000000")

        rows = asset_type_breakdown(self.user)
        by_type = {row["type"]: row for row in rows}
        self.assertEqual(by_type[AssetType.GOLD]["total"], "15000000.00")
        self.assertEqual(by_type[AssetType.GOLD]["count"], 2)
        self.assertEqual(by_type[AssetType.STOCKS]["total"], "20000000.00")

    def test_breakdown_percentages_sum_to_about_100(self):
        self._asset(AssetType.GOLD, "25000000")
        self._asset(AssetType.STOCKS, "75000000")

        rows = asset_type_breakdown(self.user)
        total_percent = sum(Decimal(row["share_percent"]) for row in rows)
        self.assertAlmostEqual(float(total_percent), 100.0, places=1)

    def test_breakdown_is_ordered_largest_first(self):
        self._asset(AssetType.STOCKS, "10000000")
        self._asset(AssetType.GOLD, "50000000")

        rows = asset_type_breakdown(self.user)
        totals = [Decimal(row["total"]) for row in rows]
        self.assertEqual(totals, sorted(totals, reverse=True))

    def test_excluded_assets_are_omitted_from_breakdown(self):
        self._asset(AssetType.GOLD, "10000000")
        self._asset(AssetType.VEHICLE, "500000000", include=False)

        rows = asset_type_breakdown(self.user)
        types = {row["type"] for row in rows}
        self.assertIn(AssetType.GOLD, types)
        self.assertNotIn(AssetType.VEHICLE, types)

    def test_empty_portfolio_returns_no_rows(self):
        self.assertEqual(asset_type_breakdown(self.user), [])


class AssetGrowthTests(TestCase):
    """``asset_growth`` returns valuation points for charting."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="growth@test.ir", password="StrongPass!234"
        )
        self.today = dt.date.today()

    def test_growth_series_is_chronological(self):
        asset = Asset.objects.create(
            user=self.user,
            name="طلا",
            asset_type=AssetType.GOLD,
            purchase_value=Decimal("120000000"),
            purchase_date=self.today - dt.timedelta(days=200),
        )
        for offset, value in [(120, "125000000"), (60, "140000000"), (0, "150000000")]:
            AssetValuation.objects.create(
                asset=asset,
                value=Decimal(value),
                valued_on=self.today - dt.timedelta(days=offset),
            )
        series = asset_growth(self.user)
        self.assertEqual(len(series), 3)
        dates = [row["date"] for row in series]
        self.assertEqual(dates, sorted(dates))
        self.assertEqual(series[-1]["value"], "150000000.00")

    def test_growth_series_records_the_asset_name(self):
        asset = Asset.objects.create(
            user=self.user,
            name="سهام فولاد",
            asset_type=AssetType.STOCKS,
            purchase_value=Decimal("45000000"),
            purchase_date=self.today,
        )
        AssetValuation.objects.create(
            asset=asset, value=Decimal("46000000"), valued_on=self.today
        )
        series = asset_growth(self.user)
        self.assertEqual(series[0]["asset_name"], "سهام فولاد")
        self.assertEqual(series[0]["asset_id"], asset.pk)

    def test_can_filter_to_a_single_asset(self):
        a = Asset.objects.create(
            user=self.user,
            name="طلا",
            asset_type=AssetType.GOLD,
            purchase_value=Decimal("10000000"),
            purchase_date=self.today,
        )
        b = Asset.objects.create(
            user=self.user,
            name="سهام",
            asset_type=AssetType.STOCKS,
            purchase_value=Decimal("20000000"),
            purchase_date=self.today,
        )
        AssetValuation.objects.create(
            asset=a, value=Decimal("11000000"), valued_on=self.today
        )
        AssetValuation.objects.create(
            asset=b, value=Decimal("21000000"), valued_on=self.today
        )
        series = asset_growth(self.user, asset_id=a.pk)
        self.assertEqual(len(series), 1)
        self.assertEqual(series[0]["asset_id"], a.pk)

    def test_no_valuations_returns_empty_series(self):
        Asset.objects.create(
            user=self.user,
            name="خودرو",
            asset_type=AssetType.VEHICLE,
            purchase_value=Decimal("500000000"),
            purchase_date=self.today,
        )
        self.assertEqual(asset_growth(self.user), [])

    def test_other_users_valuations_are_excluded(self):
        other = User.objects.create_user(
            email="other-growth@test.ir", password="StrongPass!234"
        )
        asset = Asset.objects.create(
            user=other,
            name="طلا",
            asset_type=AssetType.GOLD,
            purchase_value=Decimal("10000000"),
            purchase_date=self.today,
        )
        AssetValuation.objects.create(
            asset=asset, value=Decimal("11000000"), valued_on=self.today
        )
        self.assertEqual(asset_growth(self.user), [])
