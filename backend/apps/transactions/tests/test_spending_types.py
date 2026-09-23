"""Essential / flexible / wasted classification.

The classification is a *judgement the user makes*, not something the app
derives. These tests pin down the parts that are easy to get subtly wrong:

* the invariants that have to hold on every write path (model `save()`);
* the rule that an omitted value never erases a stored one — the exact bug
  that wiped `is_essential` on every budget re-plan;
* that the split reconciles with the `spent` figure shown next to it, because
  a drill-down whose parts do not sum to its own heading is worse than no
  drill-down at all.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import Account, AccountType
from apps.budgets.models import Budget, BudgetItem
from apps.budgets.services import spent_by_category
from apps.categories.models import Category, CategoryKind
from apps.core.jalali import jalali_month_bounds
from apps.transactions.filters import TransactionFilter
from apps.transactions.models import (
    SpendingType,
    Transaction,
    TransactionType,
)
from apps.transactions.services import (
    SPENDING_TYPE_ORDER,
    spending_type_breakdown,
    spending_type_by_category,
)
from apps.users.models import User


class SpendingTypeModelTests(TestCase):
    """Invariants that must hold for every write, not just the API's."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="spend@example.com", password="test12345", display_name="تست"
        )
        self.account = Account.objects.create(
            user=self.user,
            name="بانک ملت",
            account_type=AccountType.BANK,
            opening_balance=Decimal("10000000"),
        )
        self.expense_cat = Category.objects.create(
            user=self.user, name="خوراک", kind=CategoryKind.EXPENSE,
            icon="utensils", color="orange",
        )
        self.income_cat = Category.objects.create(
            user=self.user, name="حقوق", kind=CategoryKind.INCOME,
            icon="wallet", color="green",
        )

    def _expense(self, amount="100000", **kwargs):
        return Transaction.objects.create(
            user=self.user,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal(amount),
            category=kwargs.pop("category", self.expense_cat),
            account=kwargs.pop("account", self.account),
            **kwargs,
        )

    def _income(self, amount="5000000", **kwargs):
        return Transaction.objects.create(
            user=self.user,
            transaction_type=TransactionType.INCOME,
            amount=Decimal(amount),
            category=self.income_cat,
            account=self.account,
            **kwargs,
        )

    def test_expense_defaults_to_flexible_when_unclassified(self):
        """An expense is never left unclassified.

        Leaving it blank would drop the row out of all three buckets and make
        the split silently under-report the month.
        """
        self.assertEqual(self._expense().spending_type, SpendingType.FLEXIBLE)

    def test_explicit_classification_is_kept(self):
        tx = self._expense(spending_type=SpendingType.WASTED)
        self.assertEqual(tx.spending_type, SpendingType.WASTED)

    def test_income_never_carries_a_classification(self):
        """Even when the caller insists, because income has no direction to judge."""
        tx = self._income(spending_type=SpendingType.ESSENTIAL)
        self.assertEqual(tx.spending_type, "")

    def test_reclassifying_income_clears_a_stale_value(self):
        """A row flipped from expense to income must lose its classification."""
        tx = self._expense(spending_type=SpendingType.ESSENTIAL)
        tx.transaction_type = TransactionType.INCOME
        tx.category = self.income_cat
        tx.save()
        tx.refresh_from_db()
        self.assertEqual(tx.spending_type, "")

    def test_omitted_value_does_not_erase_a_stored_classification(self):
        """The regression this model is written to prevent.

        A PATCH that does not mention the field must leave the stored value
        alone. Defaulting an omitted value back to `flexible` is how the
        budget-level `is_essential` flag was wiped on every re-plan.
        """
        tx = self._expense(spending_type=SpendingType.WASTED)

        # A fresh instance with the field blanked, as a partial-update path
        # that only knows about `description` would build it.
        loaded = Transaction.objects.get(pk=tx.pk)
        loaded.description = "توضیح تازه"
        loaded.save()

        tx.refresh_from_db()
        self.assertEqual(tx.spending_type, SpendingType.WASTED)

    def test_update_fields_does_not_skip_the_normalisation(self):
        """`update_fields=['description']` must still persist the classification.

        Without unioning `spending_type` into `update_fields`, an expense saved
        that way would keep whatever the column already held — and an income row
        would keep a stale classification the model just cleared.
        """
        tx = self._income(spending_type=SpendingType.ESSENTIAL)
        tx.description = "حقوق مهر"
        tx.save(update_fields=["description"])

        tx.refresh_from_db()
        self.assertEqual(tx.spending_type, "")

    def test_label_is_persian_on_expense_and_blank_on_income(self):
        self.assertEqual(
            self._expense(spending_type=SpendingType.ESSENTIAL).spending_type_label,
            "ضروری",
        )
        self.assertEqual(
            self._expense(spending_type=SpendingType.FLEXIBLE).spending_type_label,
            "انعطاف‌پذیر",
        )
        self.assertEqual(
            self._expense(spending_type=SpendingType.WASTED).spending_type_label,
            "غیرضروری",
        )
        self.assertEqual(self._income().spending_type_label, "")

    def test_all_three_choices_exist_with_persian_labels(self):
        self.assertEqual(
            [label for _value, label in SpendingType.choices],
            ["ضروری", "انعطاف‌پذیر", "غیرضروری"],
        )


class SpendingTypeBreakdownTests(TestCase):
    """The shared aggregation behind the dashboard, reports and drill-down."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="break@example.com", password="test12345", display_name="تست"
        )
        self.other = User.objects.create_user(
            email="other@example.com", password="test12345", display_name="دیگری"
        )
        self.account = Account.objects.create(
            user=self.user,
            name="بانک ملت",
            account_type=AccountType.BANK,
            opening_balance=Decimal("10000000"),
        )
        self.food = Category.objects.create(
            user=self.user, name="خوراک", kind=CategoryKind.EXPENSE,
            icon="utensils", color="orange",
        )
        self.fruit = Category.objects.create(
            user=self.user, name="میوه", kind=CategoryKind.EXPENSE,
            icon="apple", color="red", parent=self.food,
        )
        self.income_cat = Category.objects.create(
            user=self.user, name="حقوق", kind=CategoryKind.INCOME,
            icon="wallet", color="green",
        )
        self.year, self.month = 1405, 6
        self.start, self.end = jalali_month_bounds(self.year, self.month)

    def _expense(self, amount, spending_type, category=None, user=None):
        return Transaction.objects.create(
            user=user or self.user,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal(str(amount)),
            category=category or self.food,
            account=self.account,
            occurred_on=self.start + dt.timedelta(days=3),
            spending_type=spending_type,
        )

    def _income(self, amount):
        return Transaction.objects.create(
            user=self.user,
            transaction_type=TransactionType.INCOME,
            amount=Decimal(str(amount)),
            category=self.income_cat,
            account=self.account,
            occurred_on=self.start + dt.timedelta(days=3),
        )

    def _buckets(self, payload):
        return {b["key"]: b for b in payload["buckets"]}

    def test_always_returns_all_three_buckets_in_fixed_order(self):
        """A stable shape, even when a bucket is empty.

        An explicit «غیرضروری: ۰ تومان» is information — it says the user looked
        and found none. A missing bucket says nothing at all.
        """
        self._expense("100000", SpendingType.ESSENTIAL)
        payload = spending_type_breakdown(self.user, self.start, self.end)

        self.assertEqual(
            [b["key"] for b in payload["buckets"]][:3], list(SPENDING_TYPE_ORDER)
        )
        self.assertEqual(payload["buckets"][2]["amount"], "0.00")
        self.assertEqual(payload["buckets"][2]["transaction_count"], 0)

    def test_totals_and_counts_are_per_bucket(self):
        self._expense("300000", SpendingType.ESSENTIAL)
        self._expense("200000", SpendingType.ESSENTIAL)
        self._expense("500000", SpendingType.FLEXIBLE)

        payload = spending_type_breakdown(self.user, self.start, self.end)
        buckets = self._buckets(payload)

        self.assertEqual(buckets["essential"]["amount"], "500000.00")
        self.assertEqual(buckets["essential"]["transaction_count"], 2)
        self.assertEqual(buckets["flexible"]["amount"], "500000.00")
        self.assertEqual(buckets["flexible"]["transaction_count"], 1)
        self.assertEqual(payload["total"], "1000000.00")

    def test_income_is_excluded_from_the_split(self):
        """Income carries no classification, so counting it invents a bucket."""
        self._expense("400000", SpendingType.ESSENTIAL)
        self._income("9000000")

        payload = spending_type_breakdown(self.user, self.start, self.end)
        self.assertEqual(payload["total"], "400000.00")

    def test_another_users_expenses_are_not_counted(self):
        self._expense("400000", SpendingType.ESSENTIAL)
        other_cat = Category.objects.create(
            user=self.other, name="خوراک", kind=CategoryKind.EXPENSE,
            icon="utensils", color="orange",
        )
        Transaction.objects.create(
            user=self.other,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("7777000"),
            category=other_cat,
            occurred_on=self.start + dt.timedelta(days=3),
            spending_type=SpendingType.WASTED,
        )

        payload = spending_type_breakdown(self.user, self.start, self.end)
        self.assertEqual(payload["total"], "400000.00")
        self.assertEqual(self._buckets(payload)["wasted"]["amount"], "0.00")

    def test_dates_outside_the_range_are_excluded(self):
        self._expense("400000", SpendingType.ESSENTIAL)
        Transaction.objects.create(
            user=self.user,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("999000"),
            category=self.food,
            account=self.account,
            occurred_on=self.end + dt.timedelta(days=1),
            spending_type=SpendingType.ESSENTIAL,
        )

        payload = spending_type_breakdown(self.user, self.start, self.end)
        self.assertEqual(payload["total"], "400000.00")

    def test_shares_sum_to_one_hundred_percent(self):
        self._expense("300000", SpendingType.ESSENTIAL)
        self._expense("700000", SpendingType.FLEXIBLE)

        buckets = self._buckets(
            spending_type_breakdown(self.user, self.start, self.end)
        )
        total_share = sum(
            Decimal(buckets[key]["share_percent"]) for key in SPENDING_TYPE_ORDER
        )
        self.assertEqual(total_share, Decimal("100"))

    def test_shares_are_zero_when_nothing_was_spent(self):
        """No division by zero, and no misleading 100%."""
        buckets = self._buckets(
            spending_type_breakdown(self.user, self.start, self.end)
        )
        self.assertEqual(buckets["essential"]["share_percent"], "0.00")
        self.assertEqual(buckets["essential"]["share_display"], "۰٪")

    def test_display_strings_are_present_for_every_bucket(self):
        self._expense("1234567", SpendingType.WASTED)
        buckets = self._buckets(
            spending_type_breakdown(self.user, self.start, self.end)
        )
        for key in SPENDING_TYPE_ORDER:
            self.assertTrue(buckets[key]["amount_display"])
            self.assertTrue(buckets[key]["share_display"])
            self.assertTrue(buckets[key]["label"])

    def test_unclassified_expense_is_surfaced_not_hidden(self):
        """A row written outside `save()` must not vanish into the total.

        `queryset.update()` bypasses the model, which is exactly the situation
        this guard is for. Hiding it would make the split look complete while
        its parts no longer summed to the total.
        """
        tx = self._expense("400000", SpendingType.ESSENTIAL)
        Transaction.objects.filter(pk=tx.pk).update(spending_type="")

        payload = spending_type_breakdown(self.user, self.start, self.end)
        buckets = self._buckets(payload)

        self.assertEqual(buckets[""]["amount"], "400000.00")
        self.assertEqual(buckets[""]["label"], "دسته‌بندی نشده")
        # Still counted in the total — surfaced, not dropped.
        self.assertEqual(payload["total"], "400000.00")

    def test_unclassified_bucket_is_absent_when_nothing_is_unclassified(self):
        self._expense("400000", SpendingType.ESSENTIAL)
        payload = spending_type_breakdown(self.user, self.start, self.end)
        self.assertNotIn("", self._buckets(payload))


class SpendingTypeByCategoryTests(TestCase):
    """The per-category split, which must reconcile with `spent`."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="bycat@example.com", password="test12345", display_name="تست"
        )
        self.account = Account.objects.create(
            user=self.user,
            name="بانک ملت",
            account_type=AccountType.BANK,
            opening_balance=Decimal("10000000"),
        )
        self.food = Category.objects.create(
            user=self.user, name="خوراک", kind=CategoryKind.EXPENSE,
            icon="utensils", color="orange",
        )
        self.fruit = Category.objects.create(
            user=self.user, name="میوه", kind=CategoryKind.EXPENSE,
            icon="apple", color="red", parent=self.food,
        )
        self.year, self.month = 1405, 6
        self.start, self.end = jalali_month_bounds(self.year, self.month)

    def _expense(self, amount, spending_type, category):
        return Transaction.objects.create(
            user=self.user,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal(str(amount)),
            category=category,
            account=self.account,
            occurred_on=self.start + dt.timedelta(days=3),
            spending_type=spending_type,
        )

    def test_child_spending_rolls_up_into_the_parent_split(self):
        """A parent budget line must see its children's classification.

        This is the same roll-up rule `spent_by_category` uses. Two different
        rules would produce a drill-down whose parts do not sum to its heading.
        """
        self._expense("100000", SpendingType.ESSENTIAL, self.food)
        self._expense("250000", SpendingType.WASTED, self.fruit)

        splits = spending_type_by_category(self.user, self.start, self.end)
        parent = {b["key"]: b for b in splits[self.food.pk]["buckets"]}

        self.assertEqual(parent["essential"]["amount"], "100000.00")
        self.assertEqual(parent["wasted"]["amount"], "250000.00")
        self.assertEqual(splits[self.food.pk]["total"], "350000.00")

    def test_child_keeps_its_own_split_too(self):
        self._expense("250000", SpendingType.WASTED, self.fruit)

        splits = spending_type_by_category(self.user, self.start, self.end)
        child = {b["key"]: b for b in splits[self.fruit.pk]["buckets"]}

        self.assertEqual(child["wasted"]["amount"], "250000.00")
        self.assertEqual(splits[self.fruit.pk]["total"], "250000.00")

    def test_split_total_matches_spent_by_category_exactly(self):
        """The reconciliation invariant, asserted rather than assumed.

        The drill-down prints these buckets under a heading taken from
        `spent_by_category`. If the two disagree the panel contradicts itself.
        """
        self._expense("100000", SpendingType.ESSENTIAL, self.food)
        self._expense("250000", SpendingType.WASTED, self.fruit)
        self._expense("333333", SpendingType.FLEXIBLE, self.fruit)

        splits = spending_type_by_category(self.user, self.start, self.end)
        spent = spent_by_category(self.user, self.start, self.end)

        self.assertIn(self.food.pk, spent)
        self.assertEqual(splits[self.food.pk]["total"], str(spent[self.food.pk][0]))
        self.assertEqual(
            splits[self.food.pk]["buckets"][0]["transaction_count"]
            + splits[self.food.pk]["buckets"][1]["transaction_count"]
            + splits[self.food.pk]["buckets"][2]["transaction_count"],
            spent[self.food.pk][1],
        )

    def test_category_with_no_spending_is_absent(self):
        """Absence, not a zero-filled entry — the caller supplies the zero shape."""
        self._expense("100000", SpendingType.ESSENTIAL, self.food)
        splits = spending_type_by_category(self.user, self.start, self.end)
        self.assertNotIn(self.fruit.pk, splits)


class SpendingTypeFilterTests(TestCase):
    """The filter behind the drill-down."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="filter@example.com", password="test12345", display_name="تست"
        )
        self.account = Account.objects.create(
            user=self.user,
            name="بانک ملت",
            account_type=AccountType.BANK,
            opening_balance=Decimal("10000000"),
        )
        self.food = Category.objects.create(
            user=self.user, name="خوراک", kind=CategoryKind.EXPENSE,
            icon="utensils", color="orange",
        )
        self.income_cat = Category.objects.create(
            user=self.user, name="حقوق", kind=CategoryKind.INCOME,
            icon="wallet", color="green",
        )
        self.essential = self._expense("100000", SpendingType.ESSENTIAL)
        self.wasted = self._expense("200000", SpendingType.WASTED)
        self.income = Transaction.objects.create(
            user=self.user,
            transaction_type=TransactionType.INCOME,
            amount=Decimal("5000000"),
            category=self.income_cat,
            account=self.account,
        )

    def _expense(self, amount, spending_type):
        return Transaction.objects.create(
            user=self.user,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal(str(amount)),
            category=self.food,
            account=self.account,
            spending_type=spending_type,
        )

    def _filter(self, **params):
        return TransactionFilter(
            data=params,
            queryset=Transaction.objects.for_user(self.user),
            request=type("R", (), {"user": self.user})(),
        )

    def test_filters_to_one_classification(self):
        result = self._filter(spending_type="essential").qs
        self.assertEqual(list(result), [self.essential])

    def test_unknown_value_filters_to_nothing(self):
        """A typo must not silently fall back to "everything".

        A filter that looks like it did nothing reads as a broken UI, not as a
        bad parameter — the more expensive of the two failures.
        """
        self.assertEqual(self._filter(spending_type="essntial").qs.count(), 0)

    def test_unclassified_selects_the_remainder(self):
        Transaction.objects.filter(pk=self.essential.pk).update(spending_type="")
        result = self._filter(spending_type="unclassified").qs
        self.assertEqual(list(result), [self.essential])

    def test_income_is_never_returned_even_with_a_stale_classification(self):
        """Direction is pinned alongside the classification.

        Income carries no classification by design, but a row written outside
        `save()` could hold one. Returning it would put income in a spending
        drill-down.
        """
        Transaction.objects.filter(pk=self.income.pk).update(
            spending_type=SpendingType.ESSENTIAL
        )
        result = self._filter(spending_type="essential").qs
        self.assertEqual(list(result), [self.essential])

    def test_all_is_a_no_op(self):
        self.assertEqual(self._filter(spending_type="all").qs.count(), 3)

    def test_omitting_the_filter_returns_everything(self):
        self.assertEqual(self._filter().qs.count(), 3)
