"""Tests for budget calculations.

These are the most important tests in the project. The budget engine decides
whether a user is told their spending is on pace or ahead of schedule, and a
wrong number here is worse than a missing feature.

Coverage:
*   Consumption percentages and remaining amounts.
*   The pace comparison (spending rate vs. time elapsed), including the exact
    examples given in the product spec.
*   Status classification across the safe → over ladder.
*   Subcategory spend rolling up into a parent budget.
*   Overspending beyond 100%, which must be reported not clamped.
*   The essential/flexible split and the flexible-budget calculation.
*   Empty months, which must not raise.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Account
from apps.budgets.models import Budget, BudgetItem
from apps.budgets.services import (
    STATUS_NEAR_LIMIT,
    STATUS_NORMAL,
    STATUS_OVER,
    STATUS_SAFE,
    analyse_budget,
    build_message,
    classify_pace,
    classify_status,
    empty_analysis,
    spent_by_category,
)
from apps.categories.models import Category, CategoryKind
from apps.core.jalali import jalali_month_bounds
from apps.transactions.models import Transaction, TransactionType

User = get_user_model()

# A fixed "today" inside شهریور ۱۴۰۵ so tests are deterministic regardless of
# when they run. 1405/06/29 falls on 2026-09-20; شهریور ۱۴۰۵ has 31 days, so
# 29 days have elapsed = 93.5%.
TEST_TODAY = dt.date(2026, 9, 20)
TEST_YEAR = 1405
TEST_MONTH = 6
TEST_MONTH_TOTAL_DAYS = 31


class BudgetTestBase(TestCase):
    """Shared fixture: one user, one account, a few categories."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="budget@example.com", password="StrongPass!234"
        )
        # A second user exists purely to prove isolation.
        cls.other_user = User.objects.create_user(
            email="other@example.com", password="StrongPass!234"
        )

        cls.account = Account.objects.create(
            user=cls.user, name="بانک ملت", opening_balance=Decimal("100000000")
        )

        cls.food = Category.objects.create(
            user=cls.user, name="خوراک", kind=CategoryKind.EXPENSE, icon="shopping-basket"
        )
        cls.groceries = Category.objects.create(
            user=cls.user, name="میوه و سبزیجات", kind=CategoryKind.EXPENSE, parent=cls.food
        )
        cls.transport = Category.objects.create(
            user=cls.user, name="حمل‌ونقل", kind=CategoryKind.EXPENSE, icon="bus"
        )
        cls.fun = Category.objects.create(
            user=cls.user, name="سرگرمی", kind=CategoryKind.EXPENSE, icon="gamepad-2"
        )
        cls.salary = Category.objects.create(
            user=cls.user, name="حقوق", kind=CategoryKind.INCOME, icon="briefcase"
        )

    def make_budget(self, items, **plan):
        """Create a شهریور ۱۴۰۵ budget with the given category amounts."""
        budget = Budget.objects.create(
            user=self.user,
            year=TEST_YEAR,
            month=TEST_MONTH,
            expected_income=plan.get("expected_income", Decimal("0.00")),
            savings_target=plan.get("savings_target", Decimal("0.00")),
            investment_target=plan.get("investment_target", Decimal("0.00")),
            debt_payment_target=plan.get("debt_payment_target", Decimal("0.00")),
        )
        for category, amount, *rest in items:
            BudgetItem.objects.create(
                budget=budget,
                category=category,
                amount=Decimal(str(amount)),
                is_essential=bool(rest and rest[0]),
            )
        return budget

    def spend(self, category, amount, *, on=None, user=None):
        """Record an expense for the test user."""
        return Transaction.objects.create(
            user=user or self.user,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal(str(amount)),
            category=category,
            account=self.account,
            occurred_on=on or TEST_TODAY,
        )

    def earn(self, amount, *, on=None):
        return Transaction.objects.create(
            user=self.user,
            transaction_type=TransactionType.INCOME,
            amount=Decimal(str(amount)),
            category=self.salary,
            account=self.account,
            occurred_on=on or TEST_TODAY,
        )


class ClassificationUnitTests(TestCase):
    """Pure-function tests for the status and pace ladders."""

    def test_status_safe_when_nothing_spent(self):
        self.assertEqual(classify_status(Decimal("0"), Decimal("0")), STATUS_SAFE)

    def test_status_safe_below_half(self):
        self.assertEqual(classify_status(Decimal("30"), Decimal("300")), STATUS_SAFE)

    def test_status_normal_in_middle(self):
        self.assertEqual(classify_status(Decimal("65"), Decimal("650")), STATUS_NORMAL)

    def test_status_near_limit_at_threshold(self):
        self.assertEqual(classify_status(Decimal("80"), Decimal("800")), STATUS_NEAR_LIMIT)
        self.assertEqual(classify_status(Decimal("99"), Decimal("990")), STATUS_NEAR_LIMIT)

    def test_status_over_above_100(self):
        self.assertEqual(classify_status(Decimal("101"), Decimal("1010")), STATUS_OVER)
        self.assertEqual(classify_status(Decimal("130"), Decimal("1300")), STATUS_OVER)

    def test_status_over_at_exactly_100_is_near_limit(self):
        """100% consumed means the budget is exhausted, not yet exceeded."""
        self.assertEqual(classify_status(Decimal("100"), Decimal("1000")), STATUS_NEAR_LIMIT)

    # --- Pace -----------------------------------------------------------

    def test_pace_ahead_when_consumption_outruns_time(self):
        # Spec example: 40% of month elapsed, 65% consumed.
        self.assertEqual(classify_pace(Decimal("65"), Decimal("40")), "ahead")

    def test_pace_behind_when_consumption_lags_time(self):
        # Spec example: 60% of month elapsed, 40% consumed.
        self.assertEqual(classify_pace(Decimal("40"), Decimal("60")), "behind")

    def test_pace_on_track_within_tolerance(self):
        self.assertEqual(classify_pace(Decimal("50"), Decimal("50")), "on_track")
        # 10 points apart is inside the 15-point tolerance.
        self.assertEqual(classify_pace(Decimal("55"), Decimal("45")), "on_track")

    def test_pace_boundary_is_exclusive(self):
        # Exactly 15 points apart is not yet "ahead".
        self.assertEqual(classify_pace(Decimal("55"), Decimal("40")), "on_track")
        self.assertEqual(classify_pace(Decimal("56"), Decimal("40")), "ahead")

    # --- Messages -------------------------------------------------------

    def test_message_is_neutral_never_accusatory(self):
        """The product must not judge the user (spec section 36)."""
        message = build_message(STATUS_NORMAL, "ahead", True, Decimal("65"), Decimal("40"))
        for accusatory in ["ضعیف", "بد", "اشتباه", "ناموفق", "بی‌دقت"]:
            self.assertNotIn(accusatory, message)

    def test_message_reflects_spec_examples(self):
        behind = build_message(STATUS_SAFE, "behind", True, Decimal("40"), Decimal("60"))
        self.assertIn("وضعیت مناسب", behind)

        ahead = build_message(STATUS_NORMAL, "ahead", True, Decimal("65"), Decimal("40"))
        self.assertIn("توجه", ahead)

    def test_message_for_no_spending(self):
        message = build_message(STATUS_SAFE, "on_track", False, Decimal("0"), Decimal("50"))
        self.assertIn("هنوز هزینه‌ای", message)

    def test_over_budget_message_wins(self):
        message = build_message(STATUS_OVER, "ahead", True, Decimal("130"), Decimal("50"))
        self.assertIn("تمام شده", message)


class BudgetAnalysisTests(BudgetTestBase):
    """End-to-end analysis against real transactions."""

    def test_nothing_spent(self):
        budget = self.make_budget([(self.food, 8_000_000)])
        analysis = analyse_budget(self.user, budget, today=TEST_TODAY)

        self.assertEqual(analysis.total_budgeted, Decimal("8000000.00"))
        self.assertEqual(analysis.total_spent, Decimal("0.00"))
        self.assertEqual(analysis.total_remaining, Decimal("8000000.00"))
        self.assertEqual(analysis.total_consumed_percent, Decimal("0.00"))

        item = analysis.categories[0]
        self.assertEqual(item.status, STATUS_SAFE)
        self.assertEqual(item.pace_state, "behind")

    def test_spec_example_80_percent_consumed(self):
        """بودجه ۲۰,۰۰۰,۰۰۰ / هزینه ۱۶,۰۰۰,۰۰۰ → ۸۰٪ مصرف شده."""
        budget = self.make_budget([(self.food, 20_000_000)])
        self.spend(self.food, 16_000_000)

        analysis = analyse_budget(self.user, budget, today=TEST_TODAY)

        self.assertEqual(analysis.total_spent, Decimal("16000000.00"))
        self.assertEqual(analysis.total_remaining, Decimal("4000000.00"))
        self.assertEqual(analysis.total_consumed_percent, Decimal("80.00"))

    def test_consumption_percentage_is_exact(self):
        budget = self.make_budget([(self.food, 8_000_000)])
        self.spend(self.food, 5_200_000)

        analysis = analyse_budget(self.user, budget, today=TEST_TODAY)
        item = analysis.categories[0]

        self.assertEqual(item.consumed_percent, Decimal("65.00"))
        self.assertEqual(item.remaining, Decimal("2800000.00"))

    def test_over_budget_is_not_clamped(self):
        """Spending 130% must report 130%, and a positive overspend amount."""
        budget = self.make_budget([(self.food, 1_000_000)])
        self.spend(self.food, 1_300_000)

        analysis = analyse_budget(self.user, budget, today=TEST_TODAY)
        item = analysis.categories[0]

        self.assertEqual(item.consumed_percent, Decimal("130.00"))
        self.assertEqual(item.status, STATUS_OVER)
        self.assertEqual(item.remaining, Decimal("-300000.00"))
        self.assertEqual(item.to_dict()["over_budget_amount"], "300000.00")

    def test_time_elapsed_matches_jalali_month_progress(self):
        budget = self.make_budget([(self.food, 1_000_000)])
        analysis = analyse_budget(self.user, budget, today=TEST_TODAY)

        # 29 of 31 days elapsed = 93.5%
        self.assertEqual(analysis.days_elapsed, 29)
        self.assertEqual(analysis.days_in_month, TEST_MONTH_TOTAL_DAYS)
        self.assertEqual(analysis.days_remaining, 2)
        self.assertEqual(analysis.elapsed_percent, Decimal("93.5"))

    def test_pace_comparison_uses_real_elapsed_time(self):
        """Late in the month, a half-spent budget should read as behind pace."""
        budget = self.make_budget([(self.food, 1_000_000)])
        self.spend(self.food, 500_000)

        analysis = analyse_budget(self.user, budget, today=TEST_TODAY)
        item = analysis.categories[0]

        # 50% consumed vs 93.5% elapsed.
        self.assertEqual(item.pace_state, "behind")
        self.assertLess(item.pace_delta, Decimal("0"))

    def test_pace_ahead_scenario(self):
        """Early in the month, most of the budget gone reads as ahead of pace."""
        # 1405/06/05 is early: 5 of 31 days = ~16%.
        early = dt.date(2026, 8, 27)
        budget = self.make_budget([(self.fun, 1_000_000)])
        self.spend(self.fun, 650_000, on=early)

        analysis = analyse_budget(self.user, budget, today=early)
        item = analysis.categories[0]

        self.assertEqual(item.consumed_percent, Decimal("65.00"))
        self.assertLess(item.elapsed_percent, Decimal("20"))
        self.assertEqual(item.pace_state, "ahead")

    def test_uncategorized_spending_counts_in_total(self):
        """Spending outside the budget still affects the month's total."""
        budget = self.make_budget([(self.food, 1_000_000)])
        self.spend(self.food, 200_000)
        self.spend(self.transport, 300_000)  # not budgeted

        analysis = analyse_budget(self.user, budget, today=TEST_TODAY)

        # Total reflects all spending; the budgeted line only its own category.
        self.assertEqual(analysis.total_spent, Decimal("500000.00"))
        self.assertEqual(analysis.categories[0].spent, Decimal("200000.00"))

    def test_transactions_outside_the_month_are_excluded(self):
        budget = self.make_budget([(self.food, 1_000_000)])
        self.spend(self.food, 100_000)  # inside
        # 1405/05/15 — previous Jalali month.
        self.spend(self.food, 900_000, on=dt.date(2026, 8, 6))

        analysis = analyse_budget(self.user, budget, today=TEST_TODAY)
        self.assertEqual(analysis.total_spent, Decimal("100000.00"))

    def test_income_spending_is_excluded(self):
        budget = self.make_budget([(self.food, 1_000_000)])
        self.spend(self.food, 100_000)
        self.earn(50_000_000)

        analysis = analyse_budget(self.user, budget, today=TEST_TODAY)

        self.assertEqual(analysis.total_spent, Decimal("100000.00"))
        self.assertEqual(analysis.actual_income, Decimal("50000000.00"))

    def test_analysis_isolation_between_users(self):
        """Another user's spending must never appear in my budget analysis."""
        budget = self.make_budget([(self.food, 1_000_000)])
        self.spend(self.food, 100_000)

        # The other user has their own categories and spending.
        other_category = Category.objects.create(
            user=self.other_user, name="خوراک", kind=CategoryKind.EXPENSE
        )
        Transaction.objects.create(
            user=self.other_user,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("9999999"),
            category=other_category,
            occurred_on=TEST_TODAY,
        )

        analysis = analyse_budget(self.user, budget, today=TEST_TODAY)
        self.assertEqual(analysis.total_spent, Decimal("100000.00"))


class SubcategoryRollupTests(BudgetTestBase):
    """Spending on a subcategory must count against the parent's budget."""

    def test_child_spending_counts_toward_parent_budget(self):
        budget = self.make_budget([(self.food, 8_000_000)])
        self.spend(self.groceries, 2_000_000)

        analysis = analyse_budget(self.user, budget, today=TEST_TODAY)

        self.assertEqual(analysis.categories[0].spent, Decimal("2000000.00"))
        self.assertEqual(analysis.categories[0].transaction_count, 1)

    def test_parent_and_child_spending_both_count(self):
        budget = self.make_budget([(self.food, 8_000_000)])
        self.spend(self.food, 1_000_000)
        self.spend(self.groceries, 2_000_000)

        analysis = analyse_budget(self.user, budget, today=TEST_TODAY)
        self.assertEqual(analysis.categories[0].spent, Decimal("3000000.00"))

    def test_spending_on_a_sibling_category_does_not_leak(self):
        budget = self.make_budget([(self.food, 8_000_000)])
        self.spend(self.groceries, 2_000_000)
        self.spend(self.transport, 5_000_000)

        analysis = analyse_budget(self.user, budget, today=TEST_TODAY)
        self.assertEqual(analysis.categories[0].spent, Decimal("2000000.00"))

    def test_spent_by_category_rolls_up(self):
        self.spend(self.groceries, 1_500_000)
        start, end = jalali_month_bounds(TEST_YEAR, TEST_MONTH)

        result = spent_by_category(self.user, start, end)

        # Both the child and the parent see the amount.
        self.assertEqual(result[self.groceries.pk][0], Decimal("1500000.00"))
        self.assertEqual(result[self.food.pk][0], Decimal("1500000.00"))


class MonthlyPlanTests(BudgetTestBase):
    """The income allocation breakdown (spec section 12)."""

    def test_spec_example_allocation(self):
        """درآمد ۳۰M، هزینه ۲۲M، پس‌انداز ۵M → بودجه آزاد ۳M."""
        budget = self.make_budget(
            [(self.food, 22_000_000)],
            expected_income=30_000_000,
            savings_target=5_000_000,
        )

        self.assertEqual(budget.allocated_total, Decimal("22000000.00"))
        self.assertEqual(budget.committed_total, Decimal("27000000.00"))
        self.assertEqual(budget.flexible_budget, Decimal("3000000.00"))
        self.assertFalse(budget.is_oversubscribed)

    def test_flexible_budget_accounts_for_all_commitments(self):
        budget = self.make_budget(
            [(self.food, 10_000_000)],
            expected_income=30_000_000,
            savings_target=5_000_000,
            investment_target=3_000_000,
            debt_payment_target=2_000_000,
        )
        # 10 + 5 + 3 + 2 = 20 committed, so 10 flexible.
        self.assertEqual(budget.committed_total, Decimal("20000000.00"))
        self.assertEqual(budget.flexible_budget, Decimal("10000000.00"))

    def test_oversubscribed_plan_is_detected(self):
        budget = self.make_budget(
            [(self.food, 25_000_000)],
            expected_income=20_000_000,
            savings_target=5_000_000,
        )
        self.assertTrue(budget.is_oversubscribed)
        self.assertEqual(budget.flexible_budget, Decimal("-10000000.00"))

    def test_essential_flexible_split(self):
        budget = self.make_budget(
            [
                (self.food, 8_000_000, True),
                (self.transport, 2_000_000, True),
                (self.fun, 1_500_000, False),
            ]
        )
        analysis = analyse_budget(self.user, budget, today=TEST_TODAY)

        self.assertEqual(analysis.essential_total, Decimal("10000000.00"))
        self.assertEqual(analysis.flexible_total, Decimal("1500000.00"))


class ProjectionTests(BudgetTestBase):
    """Mid-month extrapolation, which must be labelled as such and withheld
    when it would be meaningless."""

    def test_projection_is_produced_mid_month(self):
        budget = self.make_budget([(self.food, 3_100_000)])
        # Day 10 of 31: 1,000,000 spent so far → projected ~3,100,000.
        day_ten = dt.date(2026, 9, 1)
        self.spend(self.food, 1_000_000, on=day_ten)

        analysis = analyse_budget(self.user, budget, today=day_ten)
        item = analysis.categories[0]

        self.assertIsNotNone(item.projected_total)
        self.assertEqual(item.projected_total, Decimal("3100000.00"))

    def test_no_projection_for_a_past_month(self):
        """For a finished month the outcome is known; predicting it is noise."""
        budget = self.make_budget([(self.food, 1_000_000)])
        self.spend(self.food, 500_000)

        # Look at this budget from a much later date.
        later = dt.date(2026, 11, 15)
        analysis = analyse_budget(self.user, budget, today=later)

        self.assertIsNone(analysis.categories[0].projected_total)

    def test_no_projection_before_the_month_starts(self):
        budget = self.make_budget([(self.food, 1_000_000)])
        before = dt.date(2026, 8, 1)  # 1405/05/1x, before شهریور

        analysis = analyse_budget(self.user, budget, today=before)
        self.assertIsNone(analysis.categories[0].projected_total)


class EmptyStateTests(BudgetTestBase):
    """Months with no budget must render, not fail."""

    def test_empty_analysis_has_zero_budget(self):
        analysis = empty_analysis(self.user, TEST_YEAR, TEST_MONTH, today=TEST_TODAY)

        self.assertFalse(analysis.has_budget)
        self.assertFalse(analysis.has_items)
        self.assertEqual(analysis.total_budgeted, Decimal("0.00"))
        self.assertEqual(analysis.categories, [])

    def test_empty_analysis_still_reports_real_actuals(self):
        """A user with spending but no budget should still see their spending."""
        self.spend(self.food, 450_000)
        analysis = empty_analysis(self.user, TEST_YEAR, TEST_MONTH, today=TEST_TODAY)

        self.assertEqual(analysis.actual_expense, Decimal("450000.00"))
        self.assertEqual(analysis.total_spent, Decimal("450000.00"))

    def test_empty_analysis_serializes(self):
        payload = empty_analysis(
            self.user, TEST_YEAR, TEST_MONTH, today=TEST_TODAY
        ).to_dict()
        self.assertFalse(payload["has_budget"])
        self.assertEqual(payload["totals"]["budgeted"], "0.00")
        self.assertEqual(payload["categories"], [])

    def test_budget_with_no_items(self):
        """A plan-only budget (income defined, no categories yet)."""
        budget = self.make_budget([], expected_income=30_000_000)
        analysis = analyse_budget(self.user, budget, today=TEST_TODAY)

        self.assertTrue(analysis.has_budget)
        self.assertFalse(analysis.has_items)
        self.assertEqual(analysis.total_budgeted, Decimal("0.00"))
        self.assertEqual(analysis.total_consumed_percent, Decimal("0.00"))


class OrderingTests(BudgetTestBase):
    """Categories are ordered so the ones needing attention appear first."""

    def test_sorted_by_consumption_descending(self):
        budget = self.make_budget(
            [
                (self.food, 1_000_000),      # 0%
                (self.transport, 1_000_000),  # 50%
                (self.fun, 1_000_000),        # 95%
            ]
        )
        self.spend(self.transport, 500_000)
        self.spend(self.fun, 950_000)

        analysis = analyse_budget(self.user, budget, today=TEST_TODAY)
        order = [c.category_name for c in analysis.categories]

        self.assertEqual(order, ["سرگرمی", "حمل‌ونقل", "خوراک"])


class SerializationTests(BudgetTestBase):
    """The analysis payload must be complete and JSON-safe."""

    def test_payload_contains_everything_the_ui_needs(self):
        budget = self.make_budget([(self.food, 8_000_000)])
        self.spend(self.food, 5_200_000)

        payload = analyse_budget(self.user, budget, today=TEST_TODAY).to_dict()

        for key in ["totals", "plan", "time", "categories", "actuals"]:
            self.assertIn(key, payload)

        totals = payload["totals"]
        for key in [
            "budgeted",
            "spent",
            "remaining",
            "consumed_percent",
            "budgeted_display",
            "spent_display",
            "remaining_display",
            "consumed_display",
            "progress_ratio",
        ]:
            self.assertIn(key, totals)

        # Display strings must be Persian-formatted.
        self.assertIn("تومان", totals["spent_display"])
        self.assertIn("٪", totals["consumed_display"])

    def test_progress_ratio_is_clamped_for_the_bar(self):
        budget = self.make_budget([(self.food, 1_000_000)])
        self.spend(self.food, 1_500_000)

        payload = analyse_budget(self.user, budget, today=TEST_TODAY).to_dict()
        # Consumption reports 150% but the bar ratio clamps to 1.
        self.assertEqual(payload["totals"]["consumed_percent"], "150.00")
        self.assertEqual(payload["totals"]["progress_ratio"], "1")

    def test_payload_is_json_serializable(self):
        import json

        budget = self.make_budget([(self.food, 8_000_000)], expected_income=30_000_000)
        self.spend(self.food, 1_000_000)

        payload = analyse_budget(self.user, budget, today=TEST_TODAY).to_dict()
        # Would raise if any Decimal leaked through unstringified.
        json.dumps(payload)


class BudgetIsolationTests(BudgetTestBase):
    """A user must never see another user's budget."""

    def test_queryset_scoping(self):
        self.make_budget([(self.food, 8_000_000)])

        other_budget = Budget.objects.create(
            user=self.other_user, year=TEST_YEAR, month=TEST_MONTH
        )

        mine = Budget.objects.for_user(self.user)
        self.assertEqual(mine.count(), 1)
        self.assertNotIn(other_budget, mine)

    def test_analysis_uses_owning_user_data(self):
        budget = self.make_budget([(self.food, 1_000_000)])
        self.spend(self.food, 250_000)

        analysis = analyse_budget(self.user, budget, today=TEST_TODAY)
        self.assertEqual(analysis.total_spent, Decimal("250000.00"))
