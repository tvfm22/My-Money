"""Transaction model and calculation tests.

Transactions are the source of truth for everything else in the app — account
balances, budget spend, and reports are all derived from them. So the things
pinned down here are: amounts are always positive with direction carried by
``transaction_type``, money never goes through a float, and date filtering is
understood in Jalali.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction as db_transaction
from django.test import TestCase

from apps.accounts.models import Account, AccountType
from apps.categories.models import Category, CategoryKind
from apps.categories.services import seed_default_categories
from apps.transactions.models import Tag, Transaction, TransactionType
from apps.users.models import User


class TransactionModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="tx@test.ir", password="StrongPass!234"
        )
        self.today = dt.date.today()
        self.expense_cat = Category.objects.create(
            user=self.user,
            name="خوراک",
            kind=CategoryKind.EXPENSE,
            icon="utensils",
            color="orange",
        )
        self.income_cat = Category.objects.create(
            user=self.user,
            name="حقوق",
            kind=CategoryKind.INCOME,
            icon="wallet",
            color="green",
        )

    def _tx(self, transaction_type, amount, occurred_on=None, category=None):
        return Transaction.objects.create(
            user=self.user,
            transaction_type=transaction_type,
            amount=Decimal(amount),
            category=category
            or (
                self.expense_cat
                if transaction_type == TransactionType.EXPENSE
                else self.income_cat
            ),
            occurred_on=occurred_on or self.today,
        )

    def test_amount_is_stored_exactly(self):
        tx = self._tx(TransactionType.EXPENSE, "1234567.89")
        tx.refresh_from_db()
        # Exact round trip; a float column would drift here.
        self.assertEqual(tx.amount, Decimal("1234567.89"))

    def test_sum_of_many_small_amounts_is_exact(self):
        for _ in range(1000):
            self._tx(TransactionType.EXPENSE, "0.01")
        total = sum(t.amount for t in Transaction.objects.all())
        self.assertEqual(total, Decimal("10.00"))

    def test_expense_direction_helpers(self):
        tx = self._tx(TransactionType.EXPENSE, "50000")
        self.assertTrue(tx.is_expense)
        self.assertFalse(tx.is_income)
        self.assertEqual(tx.signed_amount, Decimal("-50000.00"))

    def test_income_direction_helpers(self):
        tx = self._tx(TransactionType.INCOME, "50000")
        self.assertTrue(tx.is_income)
        self.assertFalse(tx.is_expense)
        self.assertEqual(tx.signed_amount, Decimal("50000.00"))

    def test_zero_amount_is_rejected_by_the_database(self):
        with self.assertRaises((IntegrityError, ValidationError)):
            with db_transaction.atomic():
                self._tx(TransactionType.EXPENSE, "0")

    def test_negative_amount_is_rejected_by_the_database(self):
        """Direction is carried by transaction_type, never by a signed amount."""
        with self.assertRaises((IntegrityError, ValidationError)):
            with db_transaction.atomic():
                self._tx(TransactionType.EXPENSE, "-5000")

    def test_display_title_falls_back_to_category_name(self):
        tx = self._tx(TransactionType.EXPENSE, "50000")
        self.assertEqual(tx.display_title, "خوراک")

    def test_display_title_prefers_description(self):
        tx = self._tx(TransactionType.EXPENSE, "50000")
        tx.description = "خرید هفتگی"
        tx.save(update_fields=["description"])
        self.assertEqual(tx.display_title, "خرید هفتگی")

    def test_queryset_scoping_by_user(self):
        other = User.objects.create_user(
            email="other-tx@test.ir", password="StrongPass!234"
        )
        self._tx(TransactionType.EXPENSE, "100000")
        self.assertEqual(Transaction.objects.for_user(self.user).count(), 1)
        self.assertEqual(Transaction.objects.for_user(other).count(), 0)

    def test_expense_and_income_filters(self):
        self._tx(TransactionType.EXPENSE, "100000")
        self._tx(TransactionType.INCOME, "200000")
        self.assertEqual(Transaction.objects.for_user(self.user).expenses().count(), 1)
        self.assertEqual(Transaction.objects.for_user(self.user).incomes().count(), 1)

    def test_between_filter_is_inclusive(self):
        self._tx(TransactionType.EXPENSE, "1", occurred_on=self.today - dt.timedelta(days=5))
        self._tx(TransactionType.EXPENSE, "1", occurred_on=self.today - dt.timedelta(days=3))
        self._tx(TransactionType.EXPENSE, "1", occurred_on=self.today - dt.timedelta(days=1))

        found = Transaction.objects.for_user(self.user).between(
            self.today - dt.timedelta(days=5), self.today - dt.timedelta(days=3)
        )
        self.assertEqual(found.count(), 2)

    def test_recent_first_ordering(self):
        older = self._tx(TransactionType.EXPENSE, "1", occurred_on=self.today - dt.timedelta(days=2))
        newer = self._tx(TransactionType.EXPENSE, "1", occurred_on=self.today)
        rows = list(Transaction.objects.for_user(self.user).recent_first())
        self.assertEqual(rows[0].pk, newer.pk)
        self.assertEqual(rows[-1].pk, older.pk)


class TransactionTagTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="tag@test.ir", password="StrongPass!234"
        )
        self.category = Category.objects.create(
            user=self.user,
            name="سفر",
            kind=CategoryKind.EXPENSE,
            icon="plane",
            color="blue",
        )

    def test_tag_names_are_unique_per_user(self):
        Tag.objects.create(user=self.user, name="کاری", color="blue")
        with self.assertRaises(IntegrityError):
            with db_transaction.atomic():
                Tag.objects.create(user=self.user, name="کاری", color="red")

    def test_two_users_can_use_the_same_tag_name(self):
        other = User.objects.create_user(
            email="other-tag@test.ir", password="StrongPass!234"
        )
        Tag.objects.create(user=self.user, name="کاری", color="blue")
        Tag.objects.create(user=other, name="کاری", color="blue")
        self.assertEqual(Tag.objects.count(), 2)

    def test_tags_attach_to_transactions(self):
        tag = Tag.objects.create(user=self.user, name="کاری", color="blue")
        tx = Transaction.objects.create(
            user=self.user,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("100000"),
            category=self.category,
            occurred_on=dt.date.today(),
        )
        tx.tags.add(tag)
        self.assertEqual(tx.tags.count(), 1)
        self.assertEqual(tx.tags.first().name, "کاری")


class AccountBalanceTests(TestCase):
    """Account balance is derived, never stored, so it cannot drift."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="acct@test.ir", password="StrongPass!234"
        )
        self.today = dt.date.today()
        self.account = Account.objects.create(
            user=self.user,
            name="بانک ملت",
            account_type=AccountType.BANK,
            opening_balance=Decimal("10000000"),
        )
        self.expense_cat = Category.objects.create(
            user=self.user, name="خوراک", kind=CategoryKind.EXPENSE, icon="utensils", color="orange"
        )
        self.income_cat = Category.objects.create(
            user=self.user, name="حقوق", kind=CategoryKind.INCOME, icon="wallet", color="green"
        )

    def _tx(self, kind, amount):
        category = self.expense_cat if kind == TransactionType.EXPENSE else self.income_cat
        return Transaction.objects.create(
            user=self.user,
            transaction_type=kind,
            amount=Decimal(amount),
            category=category,
            account=self.account,
            occurred_on=self.today,
        )

    def test_balance_with_only_opening(self):
        self.assertEqual(self.account.current_balance, Decimal("10000000"))

    def test_income_increases_balance(self):
        self._tx(TransactionType.INCOME, "5000000")
        self.assertEqual(self.account.current_balance, Decimal("15000000"))

    def test_expense_decreases_balance(self):
        self._tx(TransactionType.EXPENSE, "3000000")
        self.assertEqual(self.account.current_balance, Decimal("7000000"))

    def test_balance_nets_income_and_expense(self):
        self._tx(TransactionType.INCOME, "5000000")
        self._tx(TransactionType.EXPENSE, "2000000")
        self._tx(TransactionType.EXPENSE, "1000000")
        # 10M + 5M − 3M
        self.assertEqual(self.account.current_balance, Decimal("12000000"))

    def test_balance_can_go_negative(self):
        self._tx(TransactionType.EXPENSE, "15000000")
        self.assertEqual(self.account.current_balance, Decimal("-5000000"))

    def test_deleting_a_transaction_restores_the_balance(self):
        tx = self._tx(TransactionType.EXPENSE, "3000000")
        self.assertEqual(self.account.current_balance, Decimal("7000000"))
        tx.delete()
        self.assertEqual(self.account.current_balance, Decimal("10000000"))

    def test_another_users_transactions_are_not_counted(self):
        other = User.objects.create_user(
            email="other-acct@test.ir", password="StrongPass!234"
        )
        other_cat = Category.objects.create(
            user=other, name="خوراک", kind=CategoryKind.EXPENSE, icon="utensils", color="orange"
        )
        Transaction.objects.create(
            user=other,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("999000000"),
            category=other_cat,
            account=self.account,
            occurred_on=self.today,
        )
        self.assertEqual(self.account.current_balance, Decimal("10000000"))

    def test_amounts_do_not_accumulate_float_error(self):
        for _ in range(100):
            self._tx(TransactionType.EXPENSE, "0.01")
        # 10_000_000 − 1.00 exactly.
        self.assertEqual(self.account.current_balance, Decimal("9999999.00"))


class CategoryHierarchyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="cat@test.ir", password="StrongPass!234"
        )

    def test_default_seed_creates_categories(self):
        created = seed_default_categories(self.user)
        # On first run every category is returned: 15 expense parents, their
        # 35 subcategories, and 6 income categories.
        self.assertEqual(len(created), 56)
        self.assertEqual(Category.objects.filter(user=self.user).count(), 56)
        self.assertTrue(
            Category.objects.filter(user=self.user, name="خوراک").exists()
        )

    def test_seed_splits_correctly_between_kinds(self):
        seed_default_categories(self.user)
        self.assertEqual(
            Category.objects.filter(user=self.user, kind=CategoryKind.EXPENSE).count(),
            50,
        )
        self.assertEqual(
            Category.objects.filter(user=self.user, kind=CategoryKind.INCOME).count(),
            6,
        )

    def test_seed_creates_subcategories_as_well_as_parents(self):
        seed_default_categories(self.user)
        self.assertTrue(
            Category.objects.filter(user=self.user, parent__isnull=True).exists()
        )
        self.assertTrue(
            Category.objects.filter(user=self.user, parent__isnull=False).exists()
        )

    def test_seed_is_idempotent(self):
        seed_default_categories(self.user)
        count_after_first = Category.objects.filter(user=self.user).count()

        # Second call returns the existing top-level set and creates nothing.
        second = seed_default_categories(self.user)
        count_after_second = Category.objects.filter(user=self.user).count()

        self.assertGreater(len(second), 0)
        self.assertTrue(all(c.parent is None for c in second))
        self.assertEqual(count_after_first, count_after_second)

    def test_seed_covers_both_kinds(self):
        seed_default_categories(self.user)
        self.assertTrue(
            Category.objects.filter(user=self.user, kind=CategoryKind.EXPENSE).exists()
        )
        self.assertTrue(
            Category.objects.filter(user=self.user, kind=CategoryKind.INCOME).exists()
        )

    def test_seed_assigns_icons_and_colors_from_the_design_tokens(self):
        seed_default_categories(self.user)
        for category in Category.objects.filter(user=self.user):
            self.assertTrue(category.icon, f"{category.name} has no icon")
            self.assertTrue(category.color, f"{category.name} has no color")

    def test_subcategory_reports_its_parent(self):
        parent = Category.objects.create(
            user=self.user, name="خوراک", kind=CategoryKind.EXPENSE, icon="utensils", color="orange"
        )
        child = Category.objects.create(
            user=self.user,
            name="میوه",
            kind=CategoryKind.EXPENSE,
            icon="apple",
            color="green",
            parent=parent,
        )
        self.assertTrue(child.is_subcategory)
        self.assertEqual(child.parent, parent)
        self.assertIn("خو", child.full_path)

    def test_category_cannot_be_its_own_parent(self):
        category = Category.objects.create(
            user=self.user, name="خوراک", kind=CategoryKind.EXPENSE, icon="utensils", color="orange"
        )
        category.parent = category
        with self.assertRaises((IntegrityError, ValidationError)):
            with db_transaction.atomic():
                category.save()

    def test_duplicate_name_of_same_kind_is_rejected(self):
        Category.objects.create(
            user=self.user, name="خوراک", kind=CategoryKind.EXPENSE, icon="utensils", color="orange"
        )
        with self.assertRaises(IntegrityError):
            with db_transaction.atomic():
                Category.objects.create(
                    user=self.user, name="خوراک", kind=CategoryKind.EXPENSE, icon="apple", color="green"
                )

    def test_same_name_allowed_across_different_kinds(self):
        Category.objects.create(
            user=self.user, name="هدیه", kind=CategoryKind.EXPENSE, icon="gift", color="pink"
        )
        Category.objects.create(
            user=self.user, name="هدیه", kind=CategoryKind.INCOME, icon="gift", color="pink"
        )
        self.assertEqual(Category.objects.filter(user=self.user, name="هدیه").count(), 2)

    def test_two_users_can_each_have_the_same_category(self):
        other = User.objects.create_user(
            email="other-cat@test.ir", password="StrongPass!234"
        )
        Category.objects.create(
            user=self.user, name="خوراک", kind=CategoryKind.EXPENSE, icon="utensils", color="orange"
        )
        Category.objects.create(
            user=other, name="خوراک", kind=CategoryKind.EXPENSE, icon="utensils", color="orange"
        )
        self.assertEqual(Category.objects.filter(name="خوراک").count(), 2)
