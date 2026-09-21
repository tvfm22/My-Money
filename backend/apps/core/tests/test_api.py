"""API, authentication, permission and user-isolation tests.

These are the tests that matter most from a security standpoint. Every
financial model in this app is scoped to its owner, and the API is
deny-by-default, so the two things verified here are:

1.  An unauthenticated request never reaches financial data.
2.  An authenticated user can never reach another user's rows — by list, by
    detail id, by create-with-someone-else's-id, or by writing a child object
    under someone else's parent.

The isolation tests deliberately reach for ids that *do* exist, because a
filtered list returning nothing proves less than a direct detail request
returning 404.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account, AccountType
from apps.assets.models import Asset, AssetType, AssetValuation
from apps.budgets.models import Budget, BudgetItem
from apps.categories.models import Category, CategoryKind
from apps.categories.services import seed_default_categories
from apps.core.jalali import current_jalali_month
from apps.debts.models import Debt, DebtDirection, DebtPayment
from apps.transactions.serializers import FUTURE_HORIZON_DAYS
from apps.transactions.models import Transaction, TransactionType
from apps.users.models import User

PASSWORD = "StrongPass!234"


class BaseAPITestCase(TestCase):
    """Shared fixtures: two users, each with a full set of financial rows."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            email="owner@api.ir", password=PASSWORD, display_name="صاحب"
        )
        cls.intruder = User.objects.create_user(
            email="intruder@api.ir", password=PASSWORD, display_name="مهمان"
        )
        cls.today = dt.date.today()
        cls.year, cls.month = current_jalali_month()

        # --- Owner's data -------------------------------------------------
        # The seeder already created خوراک / حقوق, so reuse them rather than
        # creating duplicates (which the unique constraint would reject).
        seed_default_categories(cls.owner)
        cls.owner_account = Account.objects.create(
            user=cls.owner,
            name="بانک ملت",
            account_type=AccountType.BANK,
            opening_balance=Decimal("50000000"),
        )
        cls.owner_category = Category.objects.get(
            user=cls.owner, name="خوراک", kind=CategoryKind.EXPENSE
        )
        cls.owner_income_category = Category.objects.get(
            user=cls.owner, name="حقوق", kind=CategoryKind.INCOME
        )
        cls.owner_tx = Transaction.objects.create(
            user=cls.owner,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("250000"),
            category=cls.owner_category,
            account=cls.owner_account,
            occurred_on=cls.today,
            description="خرید هفتگی",
        )
        cls.owner_budget = Budget.objects.create(
            user=cls.owner,
            year=cls.year,
            month=cls.month,
            expected_income=Decimal("48000000"),
        )
        BudgetItem.objects.create(
            budget=cls.owner_budget,
            category=cls.owner_category,
            amount=Decimal("8000000"),
        )
        cls.owner_debt = Debt.objects.create(
            user=cls.owner,
            direction=DebtDirection.PAYABLE,
            counterparty="بانک سامان",
            principal=Decimal("120000000"),
            issued_on=cls.today - dt.timedelta(days=200),
            due_on=cls.today + dt.timedelta(days=200),
        )
        DebtPayment.objects.create(
            debt=cls.owner_debt,
            amount=Decimal("4200000"),
            paid_on=cls.today - dt.timedelta(days=30),
        )
        cls.owner_asset = Asset.objects.create(
            user=cls.owner,
            name="صندوق طلا",
            asset_type=AssetType.GOLD_FUND,
            purchase_value=Decimal("120000000"),
            purchase_date=cls.today - dt.timedelta(days=300),
        )
        AssetValuation.objects.create(
            asset=cls.owner_asset,
            value=Decimal("150000000"),
            valued_on=cls.today,
        )

        # --- Intruder's own data (so their lists are not trivially empty) --
        seed_default_categories(cls.intruder)
        cls.intruder_account = Account.objects.create(
            user=cls.intruder,
            name="بانک سامان",
            account_type=AccountType.BANK,
            opening_balance=Decimal("1000000"),
        )
        cls.intruder_category = Category.objects.get(
            user=cls.intruder, name="حمل‌ونقل", kind=CategoryKind.EXPENSE
        )
        cls.intruder_tx = Transaction.objects.create(
            user=cls.intruder,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("90000"),
            category=cls.intruder_category,
            account=cls.intruder_account,
            occurred_on=cls.today,
        )
        cls.intruder_debt = Debt.objects.create(
            user=cls.intruder,
            direction=DebtDirection.PAYABLE,
            counterparty="دوست",
            principal=Decimal("1000000"),
            issued_on=cls.today - dt.timedelta(days=10),
            due_on=cls.today + dt.timedelta(days=10),
        )
        cls.intruder_asset = Asset.objects.create(
            user=cls.intruder,
            name="ارز",
            asset_type=AssetType.CURRENCY,
            purchase_value=Decimal("5000000"),
            purchase_date=cls.today - dt.timedelta(days=50),
        )

    def setUp(self):
        self.client = APIClient()
        self.intruder_client = APIClient()
        self.intruder_client.force_authenticate(self.intruder)

    def auth(self):
        """Authenticate the default client as the owner."""
        self.client.force_authenticate(self.owner)
        return self.client


class AuthenticationTests(BaseAPITestCase):
    """Endpoints are deny-by-default; unauthenticated access must be refused."""

    def test_protected_endpoints_reject_anonymous(self):
        endpoints = [
            "/api/dashboard/",
            "/api/transactions/",
            "/api/accounts/",
            "/api/categories/",
            "/api/budgets/",
            "/api/debts/",
            "/api/assets/",
            "/api/reports/",
            "/api/insights/",
            "/api/auth/me/",
        ]
        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                response = self.client.get(endpoint)
                self.assertIn(
                    response.status_code,
                    (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
                    f"{endpoint} was reachable without authentication",
                )

    def test_health_endpoint_is_public(self):
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_register_creates_a_usable_account(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "email": "new@api.ir",
                "password": PASSWORD,
                "password_confirm": PASSWORD,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(User.objects.filter(email="new@api.ir").exists())

    def test_register_seeds_default_categories(self):
        self.client.post(
            "/api/auth/register/",
            {
                "email": "seeded@api.ir",
                "password": PASSWORD,
                "password_confirm": PASSWORD,
            },
            format="json",
        )
        user = User.objects.get(email="seeded@api.ir")
        # A brand-new user must land on a populated app, not an empty one.
        self.assertTrue(Category.objects.filter(user=user).exists())

    def test_register_rejects_mismatched_passwords(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "email": "mismatch@api.ir",
                "password": PASSWORD,
                "password_confirm": "SomethingElse!234",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_rejects_weak_password(self):
        response = self.client.post(
            "/api/auth/register/",
            {"email": "weak@api.ir", "password": "123", "password_confirm": "123"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_rejects_duplicate_email(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "email": self.owner.email,
                "password": PASSWORD,
                "password_confirm": PASSWORD,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_returns_tokens(self):
        response = self.client.post(
            "/api/auth/login/",
            {"email": self.owner.email, "password": PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_login_rejects_wrong_password(self):
        response = self.client.post(
            "/api/auth/login/",
            {"email": self.owner.email, "password": "WrongPassword!234"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_error_message_is_persian(self):
        response = self.client.post(
            "/api/auth/login/",
            {"email": self.owner.email, "password": "WrongPassword!234"},
            format="json",
        )
        body = str(response.data)
        self.assertTrue(
            any("\u0600" <= ch <= "\u06ff" for ch in body),
            f"login error was not in Persian: {body}",
        )

    def test_me_returns_the_authenticated_user(self):
        response = self.auth().get("/api/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], self.owner.email)


class UserIsolationTests(BaseAPITestCase):
    """A second account must never reach the first account's financial rows."""

    def test_list_endpoints_only_return_own_rows(self):
        client = self.auth()
        cases = [
            ("/api/transactions/", self.owner_tx.pk),
            ("/api/accounts/", self.owner_account.pk),
            ("/api/debts/", self.owner_debt.pk),
            ("/api/assets/", self.owner_asset.pk),
        ]
        for endpoint, own_id in cases:
            with self.subTest(endpoint=endpoint):
                response = client.get(endpoint)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                results = response.data.get("results", response.data)
                ids = [row["id"] for row in results]
                self.assertIn(own_id, ids)

    def test_intruder_list_counts_exclude_owner_rows(self):
        # The intruder has exactly one of each, and must not see the owner's.
        expectations = [
            ("/api/transactions/", 1),
            ("/api/accounts/", 1),
            ("/api/debts/", 1),
            ("/api/assets/", 1),
        ]
        for endpoint, expected in expectations:
            with self.subTest(endpoint=endpoint):
                response = self.intruder_client.get(endpoint)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                results = response.data.get("results", response.data)
                self.assertEqual(
                    len(results),
                    expected,
                    f"{endpoint} leaked rows across users",
                )

    def test_intruder_cannot_read_owner_transaction_by_id(self):
        response = self.intruder_client.get(f"/api/transactions/{self.owner_tx.pk}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_intruder_cannot_read_owner_account_by_id(self):
        response = self.intruder_client.get(f"/api/accounts/{self.owner_account.pk}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_intruder_cannot_read_owner_debt_by_id(self):
        response = self.intruder_client.get(f"/api/debts/{self.owner_debt.pk}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_intruder_cannot_read_owner_asset_by_id(self):
        response = self.intruder_client.get(f"/api/assets/{self.owner_asset.pk}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_intruder_cannot_delete_owner_transaction(self):
        response = self.intruder_client.delete(
            f"/api/transactions/{self.owner_tx.pk}/"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Transaction.objects.filter(pk=self.owner_tx.pk).exists())

    def test_intruder_cannot_update_owner_account(self):
        response = self.intruder_client.patch(
            f"/api/accounts/{self.owner_account.pk}/",
            {"name": "hijacked"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.owner_account.refresh_from_db()
        self.assertEqual(self.owner_account.name, "بانک ملت")

    def test_intruder_cannot_attach_a_transaction_to_owner_category(self):
        """Creating a row with someone else's FK must be rejected, not silently accepted."""
        response = self.intruder_client.post(
            "/api/transactions/",
            {
                "transaction_type": TransactionType.EXPENSE,
                "amount": "100000",
                "category": self.owner_category.pk,
                "occurred_on": self.today.isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_intruder_cannot_attach_a_transaction_to_owner_account(self):
        response = self.intruder_client.post(
            "/api/transactions/",
            {
                "transaction_type": TransactionType.EXPENSE,
                "amount": "100000",
                "category": self.intruder_category.pk,
                "account": self.owner_account.pk,
                "occurred_on": self.today.isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_intruder_cannot_pay_owner_debt(self):
        before = self.owner_debt.paid_amount
        response = self.intruder_client.post(
            f"/api/debts/{self.owner_debt.pk}/payments/",
            {"amount": "1000000", "paid_on": self.today.isoformat()},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.owner_debt.refresh_from_db()
        self.assertEqual(self.owner_debt.paid_amount, before)

    def test_intruder_cannot_add_a_valuation_to_owner_asset(self):
        response = self.intruder_client.post(
            f"/api/assets/{self.owner_asset.pk}/valuations/",
            {"value": "999999999", "valued_on": self.today.isoformat()},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.owner_asset.refresh_from_db()
        self.assertEqual(self.owner_asset.current_value, Decimal("150000000"))

    def test_intruder_budget_analysis_never_shows_owner_categories(self):
        response = self.intruder_client.get("/api/budgets/analysis/")
        self.assertIn(response.status_code, (200, 404))
        if response.status_code == 200:
            self.assertNotIn("خوراک", str(response.data))

    def test_dashboard_totals_are_scoped_to_the_caller(self):
        owner_dashboard = self.auth().get("/api/dashboard/")
        self.assertEqual(owner_dashboard.status_code, status.HTTP_200_OK)

        intruder_dashboard = self.intruder_client.get("/api/dashboard/")
        self.assertEqual(intruder_dashboard.status_code, status.HTTP_200_OK)

        # The owner holds 50M opening plus far more assets; the two payloads
        # must not be identical.
        self.assertNotEqual(
            owner_dashboard.data["summary"]["balance"],
            intruder_dashboard.data["summary"]["balance"],
        )

    def test_reports_are_scoped_to_the_caller(self):
        owner_report = self.auth().get("/api/reports/")
        self.assertEqual(owner_report.status_code, status.HTTP_200_OK)
        intruder_report = self.intruder_client.get("/api/reports/")
        self.assertEqual(intruder_report.status_code, status.HTTP_200_OK)
        self.assertNotEqual(owner_report.data, intruder_report.data)


class TransactionAPITests(BaseAPITestCase):
    """Behaviour of the transaction endpoints themselves."""

    def test_create_returns_display_fields(self):
        response = self.auth().post(
            "/api/transactions/",
            {
                "transaction_type": TransactionType.EXPENSE,
                "amount": "345000",
                "category": self.owner_category.pk,
                "account": self.owner_account.pk,
                "occurred_on": self.today.isoformat(),
                "description": "تست",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        # Derived, pre-formatted fields must be present on the create response,
        # so the client does not have to re-fetch or compute a display string.
        self.assertIsNotNone(response.data["amount_display"])
        self.assertIsNotNone(response.data["date_display"])
        self.assertEqual(response.data["amount"], "345000.00")

    def test_create_accepts_persian_digits_in_amount(self):
        response = self.auth().post(
            "/api/transactions/",
            {
                "transaction_type": TransactionType.EXPENSE,
                "amount": "۳۴۵۰۰۰",
                "category": self.owner_category.pk,
                "occurred_on": self.today.isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["amount"], "345000.00")

    def test_create_accepts_a_jalali_date_string(self):
        jalali = f"{self.year}/{self.month:02d}/05"
        response = self.auth().post(
            "/api/transactions/",
            {
                "transaction_type": TransactionType.EXPENSE,
                "amount": "100000",
                "category": self.owner_category.pk,
                "occurred_on": jalali,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_expense_with_income_category_is_rejected(self):
        response = self.auth().post(
            "/api/transactions/",
            {
                "transaction_type": TransactionType.EXPENSE,
                "amount": "100000",
                "category": self.owner_income_category.pk,
                "occurred_on": self.today.isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_zero_amount_is_rejected(self):
        response = self.auth().post(
            "/api/transactions/",
            {
                "transaction_type": TransactionType.EXPENSE,
                "amount": "0",
                "category": self.owner_category.pk,
                "occurred_on": self.today.isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_near_future_date_is_accepted(self):
        """A future date is legitimate: a scheduled payment or a post-dated cheque.

        It is deliberately permitted because the spent-per-category aggregation
        is range-filtered, so a future-dated row lands in its own month's bucket
        and cannot distort the current month's totals. Some slack is allowed on
        top of the horizon so a user in a timezone ahead of the server is not
        blocked when recording something dated "today" locally.
        """
        future = self.today + dt.timedelta(days=45)
        response = self.auth().post(
            "/api/transactions/",
            {
                "transaction_type": TransactionType.EXPENSE,
                "amount": "100000",
                "category": self.owner_category.pk,
                "occurred_on": future.isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_far_future_date_is_rejected(self):
        """Beyond the horizon it is a typo, not a plan, so it is refused."""
        too_far = self.today + dt.timedelta(days=FUTURE_HORIZON_DAYS + 30)
        response = self.auth().post(
            "/api/transactions/",
            {
                "transaction_type": TransactionType.EXPENSE,
                "amount": "100000",
                "category": self.owner_category.pk,
                "occurred_on": too_far.isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_amounts_are_returned_as_strings_never_floats(self):
        response = self.auth().get("/api/transactions/")
        results = response.data.get("results", response.data)
        for row in results:
            self.assertIsInstance(
                row["amount"],
                str,
                "amount must serialize as a string so JSON floats cannot lose precision",
            )

    def test_summary_endpoint_totals_are_correct(self):
        Transaction.objects.create(
            user=self.owner,
            transaction_type=TransactionType.INCOME,
            amount=Decimal("10000000"),
            category=self.owner_income_category,
            account=self.owner_account,
            occurred_on=self.today,
        )
        response = self.auth().get("/api/transactions/summary/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            Decimal(response.data["income_total"]), Decimal("10000000.00")
        )
        self.assertEqual(
            Decimal(response.data["expense_total"]), Decimal("250000.00")
        )
        self.assertEqual(Decimal(response.data["net"]), Decimal("9750000.00"))

    def test_filter_by_transaction_type(self):
        response = self.auth().get("/api/transactions/?transaction_type=expense")
        results = response.data.get("results", response.data)
        self.assertTrue(all(r["transaction_type"] == "expense" for r in results))

    def test_filter_by_month_uses_jalali_keys(self):
        response = self.auth().get(f"/api/transactions/?month={self.year}-{self.month:02d}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        self.assertIn(self.owner_tx.pk, [r["id"] for r in results])

    def test_filter_by_amount_range_accepts_persian_digits(self):
        response = self.auth().get("/api/transactions/?amount_min=۲۰۰۰۰۰")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        self.assertIn(self.owner_tx.pk, [r["id"] for r in results])

    def test_recent_endpoint_respects_its_limit(self):
        for i in range(10):
            Transaction.objects.create(
                user=self.owner,
                transaction_type=TransactionType.EXPENSE,
                amount=Decimal("1000"),
                category=self.owner_category,
                occurred_on=self.today - dt.timedelta(days=i),
            )
        response = self.auth().get("/api/transactions/recent/?limit=5")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # `recent` returns a bare list, not a paginated envelope — it is used
        # for the dashboard strip where a page envelope would be noise.
        self.assertIsInstance(response.data, list)
        self.assertEqual(len(response.data), 5)

    def test_delete_removes_the_row(self):
        response = self.auth().delete(f"/api/transactions/{self.owner_tx.pk}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Transaction.objects.filter(pk=self.owner_tx.pk).exists())


class AccountAPITests(BaseAPITestCase):
    def test_balance_is_derived_from_transactions(self):
        response = self.auth().get(f"/api/accounts/{self.owner_account.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # 50M opening − 250k expense.
        self.assertEqual(
            Decimal(response.data["current_balance"]), Decimal("49750000.00")
        )

    def test_balance_updates_after_adding_a_transaction(self):
        self.auth().post(
            "/api/transactions/",
            {
                "transaction_type": TransactionType.EXPENSE,
                "amount": "1000000",
                "category": self.owner_category.pk,
                "account": self.owner_account.pk,
                "occurred_on": self.today.isoformat(),
            },
            format="json",
        )
        response = self.auth().get(f"/api/accounts/{self.owner_account.pk}/")
        self.assertEqual(
            Decimal(response.data["current_balance"]), Decimal("48750000.00")
        )

    def test_delete_refuses_when_transactions_exist(self):
        response = self.auth().delete(f"/api/accounts/{self.owner_account.pk}/")
        # Deleting an account with history would silently destroy it.
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertTrue(Account.objects.filter(pk=self.owner_account.pk).exists())


class CategoryAPITests(BaseAPITestCase):
    def test_delete_refuses_when_transactions_exist(self):
        response = self.auth().delete(f"/api/categories/{self.owner_category.pk}/")
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertTrue(Category.objects.filter(pk=self.owner_category.pk).exists())

    def test_meta_endpoint_exposes_icons_and_colors(self):
        response = self.auth().get("/api/categories/meta/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Options come from the server so the client hardcodes no design tokens.
        self.assertIn("icons", response.data)
        self.assertIn("colors", response.data)
        self.assertGreater(len(response.data["icons"]), 10)

    def test_cannot_create_a_category_with_an_unknown_icon(self):
        response = self.auth().post(
            "/api/categories/",
            {
                "name": "دسته تازه",
                "kind": CategoryKind.EXPENSE,
                "icon": "not-a-real-icon-name",
                "color": "orange",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class BudgetAPITests(BaseAPITestCase):
    def test_analysis_matches_the_spec_example(self):
        """۲۰,۰۰۰,۰۰۰ بودجه / ۱۶,۰۰۰,۰۰۰ هزینه → ۸۰٪ مصرف."""
        # The fixture already created this month's budget, so reuse it and
        # replace its single item with the amount the example calls for.
        budget = self.owner_budget
        budget.items.all().delete()
        BudgetItem.objects.create(
            budget=budget, category=self.owner_category, amount=Decimal("20000000")
        )

        # Clear the fixture transaction and record exactly 16M instead.
        Transaction.objects.filter(user=self.owner).delete()
        Transaction.objects.create(
            user=self.owner,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("16000000"),
            category=self.owner_category,
            occurred_on=self.today,
        )

        response = self.auth().get(f"/api/budgets/{budget.pk}/analysis/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        results = response.data.get("results", response.data)
        # Find the خوراک line and assert it reads exactly 80%.
        categories = results.get("categories", [])
        line = next(
            (c for c in categories if c["category_name"] == self.owner_category.name),
            None,
        )
        self.assertIsNotNone(line, f"خوراک missing from analysis: {categories}")
        self.assertEqual(Decimal(line["consumed_percent"]), Decimal("80.00"))
        self.assertEqual(Decimal(line["budgeted"]), Decimal("20000000.00"))
        self.assertEqual(Decimal(line["spent"]), Decimal("16000000.00"))
        self.assertEqual(Decimal(line["remaining"]), Decimal("4000000.00"))

    def test_analysis_never_uses_accusatory_language(self):
        response = self.auth().get("/api/budgets/analysis/")
        self.assertIn(response.status_code, (200, 404))
        if response.status_code == 200:
            payload = str(response.data)
            for word in ["ضعیف", "اشتباه", "ناموفق", "بی‌دقت"]:
                self.assertNotIn(word, payload)

    def test_analysis_honours_the_year_and_month_pair(self):
        """`?year=&month=` must select that month — not silently show this one.

        The web client navigates by sending the pair, and the view previously
        understood only `?month=1405-06`, so it fell back to the current month
        and the date filter appeared to do nothing.
        """
        # A budget for a neighbouring month, deliberately distinguishable.
        other_year, other_month = (
            (self.year, self.month - 1) if self.month > 1 else (self.year - 1, 12)
        )
        Budget.objects.filter(user=self.owner).delete()
        Budget.objects.create(
            user=self.owner,
            year=other_year,
            month=other_month,
            expected_income=Decimal("11111111"),
        )

        response = self.auth().get(
            "/api/budgets/analysis/",
            {"year": other_year, "month": other_month},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        results = response.data.get("results", response.data)
        # The payload carries the resolved month as flat keys, so this is the
        # direct assertion that the filter was honoured.
        self.assertEqual(results["year"], other_year)
        self.assertEqual(results["month"], other_month)
        # The fixture budget belongs to the current month, so this proves the
        # requested month was used rather than the default.
        self.assertTrue(results["has_budget"])
        self.assertEqual(
            Decimal(results["plan"]["expected_income"]), Decimal("11111111.00")
        )

    def test_analysis_accepts_the_packed_month_form(self):
        response = self.auth().get(
            "/api/budgets/analysis/", {"month": f"{self.year}-{self.month:02d}"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        results = response.data.get("results", response.data)
        self.assertEqual(results["year"], self.year)
        self.assertEqual(results["month"], self.month)

    def test_analysis_falls_back_to_this_month_on_a_bad_filter(self):
        """A junk filter shows something rather than erroring."""
        response = self.auth().get("/api/budgets/analysis/", {"year": 1405, "month": 99})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        results = response.data.get("results", response.data)
        self.assertEqual(results["year"], self.year)
        self.assertEqual(results["month"], self.month)

    def test_month_label_is_identical_with_and_without_a_budget(self):
        """The label must not change digit style just because a budget exists.

        `empty_analysis` built the label without the digit conversion while
        `Budget.label` used it, so a month with a budget read `شهریور ۱۴۰۵` and
        one without read `فروردین 1405` — two numeral systems for the same
        concept in the same response shape.
        """
        with_budget = self.auth().get(
            "/api/budgets/analysis/", {"year": self.year, "month": self.month}
        )
        self.assertEqual(with_budget.status_code, status.HTTP_200_OK)
        budgeted_label = with_budget.data.get("results", with_budget.data)["label"]
        self.assertTrue(with_budget.data.get("results", with_budget.data)["has_budget"])

        # A month the fixture deliberately left without a budget.
        other_month = 12 if self.month != 12 else 11
        without_budget = self.auth().get(
            "/api/budgets/analysis/", {"year": self.year, "month": other_month}
        )
        self.assertEqual(without_budget.status_code, status.HTTP_200_OK)
        empty = without_budget.data.get("results", without_budget.data)
        self.assertFalse(empty["has_budget"])

        def has_persian_digit(text):
            return any("۰" <= c <= "۹" for c in text)

        def has_latin_digit(text):
            return any("0" <= c <= "9" for c in text)

        self.assertTrue(has_persian_digit(budgeted_label), budgeted_label)
        self.assertTrue(has_persian_digit(empty["label"]), empty["label"])
        self.assertFalse(has_latin_digit(empty["label"]), empty["label"])
        self.assertFalse(has_latin_digit(budgeted_label), budgeted_label)

    def test_plan_persists_the_allocations_it_is_sent(self):
        """The request key is `allocations`, and the amounts must survive.

        The client used to POST `items`. DRF ignores keys a serializer does not
        declare, so the request returned 200, the income updated, and every line
        amount was dropped — editing a budget and pressing save looked like it
        worked and changed nothing. This test pins the working key.
        """
        response = self.auth().post(
            "/api/budgets/plan/",
            {
                "year": self.year,
                "month": self.month,
                "expected_income": "50000000",
                "allocations": [
                    {"category": self.owner_category.pk, "amount": "7000000"},
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        item = BudgetItem.objects.get(
            budget=self.owner_budget, category=self.owner_category
        )
        self.assertEqual(item.amount, Decimal("7000000.00"))

    def test_plan_silently_ignores_an_undeclared_key(self):
        """Documents the trap rather than pretending it cannot happen.

        An unknown key is not an error — DRF drops it. That is why the mismatch
        above was invisible for so long, and why the working key needs a test of
        its own rather than being assumed.
        """
        before = BudgetItem.objects.filter(budget=self.owner_budget).count()

        response = self.auth().post(
            "/api/budgets/plan/",
            {
                "year": self.year,
                "month": self.month,
                "expected_income": "12345678",
                # The wrong key, deliberately.
                "items": [{"category": self.owner_category.pk, "amount": "9999999"}],
            },
            format="json",
        )

        # Accepted, and nothing happened to the lines.
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(
            BudgetItem.objects.filter(budget=self.owner_budget).count(), before
        )
        self.assertFalse(
            BudgetItem.objects.filter(
                budget=self.owner_budget, amount=Decimal("9999999.00")
            ).exists()
        )

    def test_plan_keeps_is_essential_when_the_flag_is_omitted(self):
        """Omitting the flag means "leave it alone", not "make it flexible".

        The serializer used to coerce a missing flag to `False` and the view
        wrote it through `update_or_create`, so any save that did not mention the
        flag erased it. A line the user had marked non-negotiable silently became
        flexible on the next edit, changing the essential/flexible split without
        anyone touching it.
        """
        # Establish an essential line.
        self.auth().post(
            "/api/budgets/plan/",
            {
                "year": self.year,
                "month": self.month,
                "expected_income": "50000000",
                "allocations": [
                    {
                        "category": self.owner_category.pk,
                        "amount": "7000000",
                        "is_essential": True,
                    },
                ],
            },
            format="json",
        )
        item = BudgetItem.objects.get(
            budget=self.owner_budget, category=self.owner_category
        )
        self.assertTrue(item.is_essential)

        # Save again, changing only the amount and saying nothing about the flag.
        self.auth().post(
            "/api/budgets/plan/",
            {
                "year": self.year,
                "month": self.month,
                "expected_income": "50000000",
                "allocations": [
                    {"category": self.owner_category.pk, "amount": "8000000"},
                ],
            },
            format="json",
        )

        item.refresh_from_db()
        self.assertEqual(item.amount, Decimal("8000000.00"))
        self.assertTrue(
            item.is_essential,
            "an omitted is_essential must not clear a stored True",
        )

    def test_plan_can_explicitly_clear_is_essential(self):
        """The flip side: saying `false` must actually clear it."""
        self.auth().post(
            "/api/budgets/plan/",
            {
                "year": self.year,
                "month": self.month,
                "expected_income": "50000000",
                "allocations": [
                    {
                        "category": self.owner_category.pk,
                        "amount": "7000000",
                        "is_essential": True,
                    },
                ],
            },
            format="json",
        )

        self.auth().post(
            "/api/budgets/plan/",
            {
                "year": self.year,
                "month": self.month,
                "expected_income": "50000000",
                "allocations": [
                    {
                        "category": self.owner_category.pk,
                        "amount": "7000000",
                        "is_essential": False,
                    },
                ],
            },
            format="json",
        )

        item = BudgetItem.objects.get(
            budget=self.owner_budget, category=self.owner_category
        )
        self.assertFalse(item.is_essential)

    def test_duplicate_budget_for_same_month_is_rejected(self):
        response = self.auth().post(
            "/api/budgets/",
            {
                "year": self.year,
                "month": self.month,
                "expected_income": "50000000",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class DebtAPITests(BaseAPITestCase):
    def test_payment_updates_remaining_and_status(self):
        response = self.auth().post(
            f"/api/debts/{self.owner_debt.pk}/payments/",
            {"amount": "10000000", "paid_on": self.today.isoformat()},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.owner_debt.refresh_from_db()
        self.assertEqual(self.owner_debt.paid_amount, Decimal("14200000.00"))
        self.assertEqual(self.owner_debt.status, "partial")

    def test_overpayment_is_rejected_with_a_persian_message(self):
        response = self.auth().post(
            f"/api/debts/{self.owner_debt.pk}/payments/",
            {"amount": "999999999", "paid_on": self.today.isoformat()},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(
            any("\u0600" <= ch <= "\u06ff" for ch in str(response.data)),
            f"overpayment error was not in Persian: {response.data}",
        )

    def test_summary_totals_are_scoped(self):
        response = self.auth().get("/api/debts/summary/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # 120M principal − 4.2M paid.
        self.assertEqual(
            Decimal(response.data["payable_remaining"]), Decimal("115800000.00")
        )


class AssetAPITests(BaseAPITestCase):
    def test_current_value_reflects_the_latest_valuation(self):
        response = self.auth().get(f"/api/assets/{self.owner_asset.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            Decimal(response.data["current_value"]), Decimal("150000000.00")
        )

    def test_summary_includes_net_worth(self):
        response = self.auth().get("/api/assets/summary/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("net_worth", response.data)
        self.assertEqual(
            Decimal(response.data["net_worth"]["net_worth"]),
            Decimal("34200000.00"),  # 150M asset − 115.8M debt
        )

    def test_net_worth_history_returns_points(self):
        response = self.auth().get("/api/net-worth/history/?months=6")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Enveloped as {"history": [...]} so the payload can carry a change
        # summary alongside the series.
        self.assertIn("history", response.data)
        self.assertEqual(len(response.data["history"]), 6)

    def test_net_worth_endpoint_computes_the_same_figure_as_the_summary(self):
        summary = self.auth().get("/api/assets/summary/")
        standalone = self.auth().get("/api/net-worth/")
        self.assertEqual(standalone.status_code, status.HTTP_200_OK)
        self.assertEqual(
            Decimal(standalone.data["net_worth"]),
            Decimal(summary.data["net_worth"]["net_worth"]),
        )

    def test_valuation_duplicate_date_is_rejected(self):
        response = self.auth().post(
            f"/api/assets/{self.owner_asset.pk}/valuations/",
            {"value": "160000000", "valued_on": self.today.isoformat()},
            format="json",
        )
        # One value per asset per day; the constraint is enforced, not silent.
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class DashboardAndReportAPITests(BaseAPITestCase):
    def test_dashboard_returns_every_section_the_home_screen_needs(self):
        response = self.auth().get("/api/dashboard/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for key in ["month", "summary", "budget", "recent_transactions"]:
            self.assertIn(key, response.data, f"dashboard is missing '{key}'")

    def test_dashboard_summary_contains_the_headline_figures(self):
        response = self.auth().get("/api/dashboard/")
        summary = response.data["summary"]
        for key in [
            "balance",
            "income",
            "expense",
            "net",
            "spendable",
            "total_assets",
            "total_debts",
            "total_receivables",
            "net_worth",
        ]:
            self.assertIn(key, summary, f"summary is missing '{key}'")

    def test_dashboard_month_is_jalali(self):
        response = self.auth().get("/api/dashboard/")
        month = response.data["month"]
        self.assertEqual(month["year"], self.year)
        self.assertEqual(month["month"], self.month)

    def test_reports_payload_contains_all_charts(self):
        response = self.auth().get("/api/reports/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for key in ["spending_by_category", "monthly_trend", "budget_vs_actual"]:
            self.assertIn(key, response.data, f"reports is missing '{key}'")

    def test_monthly_trend_accepts_a_month_count(self):
        response = self.auth().get("/api/reports/monthly-trend/?months=6")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Returns {"series": [...], "months": n} rather than a bare list.
        self.assertIn("series", response.data)
        self.assertEqual(len(response.data["series"]), 6)
        self.assertEqual(response.data["months"], 6)

    def test_monthly_trend_series_carries_jalali_labels(self):
        response = self.auth().get("/api/reports/monthly-trend/?months=3")
        for row in response.data["series"]:
            # Persian month name, not a Gregorian month label.
            self.assertTrue(
                any("\u0600" <= ch <= "\u06ff" for ch in row["label"]),
                f"trend label was not Persian: {row['label']}",
            )
            self.assertNotIn("2026", row["label"])

    def test_insights_are_returned_in_persian(self):
        response = self.auth().get("/api/insights/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        items = response.data if isinstance(response.data, list) else response.data.get("insights", [])
        self.assertGreater(len(items), 0, "a populated account should yield insights")
        for item in items:
            self.assertTrue(
                any("\u0600" <= ch <= "\u06ff" for ch in item["message"]),
                f"insight message was not in Persian: {item['message']}",
            )

    def test_every_insight_carries_its_supporting_metric(self):
        """An insight without its underlying numbers cannot be audited."""
        response = self.auth().get("/api/insights/")
        items = response.data if isinstance(response.data, list) else response.data.get("insights", [])
        for item in items:
            self.assertIn("metric", item)
