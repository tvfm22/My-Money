"""Debt calculation tests.

Debt arithmetic is money arithmetic with state on top, so the things that
matter here are: partial payments never produce a negative remainder, the
derived status always agrees with the underlying numbers, overpayment is
refused rather than silently clamped, and one user can never see or pay
another user's debt.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.test import TestCase

from apps.core.jalali import format_jalali
from apps.transactions.serializers import FUTURE_HORIZON_DAYS
from apps.debts.models import Debt, DebtDirection, DebtPayment, DebtStatus
from apps.debts.serializers import DebtPaymentWriteSerializer
from apps.users.models import User


class DebtCalculationTests(TestCase):
    """Pure calculation behaviour on a single debt."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="debt@test.ir", password="StrongPass!234"
        )
        self.today = dt.date.today()

    def _debt(self, principal="10000000", due_on=None, direction=DebtDirection.PAYABLE):
        return Debt.objects.create(
            user=self.user,
            direction=direction,
            counterparty="بانک تست",
            principal=Decimal(principal),
            issued_on=self.today - dt.timedelta(days=60),
            due_on=due_on or (self.today + dt.timedelta(days=30)),
        )

    def test_no_payments_means_zero_paid(self):
        debt = self._debt("5000000")
        self.assertEqual(debt.paid_amount, Decimal("0"))
        self.assertEqual(debt.remaining_amount, Decimal("5000000"))
        self.assertEqual(debt.paid_percent, Decimal("0"))

    def test_partial_payment_reduces_remaining_exactly(self):
        debt = self._debt("10000000")
        DebtPayment.objects.create(
            debt=debt, amount=Decimal("3500000"), paid_on=self.today
        )
        self.assertEqual(debt.paid_amount, Decimal("3500000"))
        self.assertEqual(debt.remaining_amount, Decimal("6500000"))
        self.assertEqual(debt.paid_percent, Decimal("35.00"))

    def test_multiple_payments_sum_exactly(self):
        debt = self._debt("3000000")
        for amount in ("1000000", "500000.50", "499999.50"):
            DebtPayment.objects.create(
                debt=debt, amount=Decimal(amount), paid_on=self.today
            )
        # 1_000_000 + 500_000.50 + 499_999.50 == 2_000_000 exactly. A float
        # pipeline would land on 1999999.9999999998 here.
        self.assertEqual(debt.paid_amount, Decimal("2000000"))
        self.assertEqual(debt.remaining_amount, Decimal("1000000"))

    def test_full_payment_settles(self):
        debt = self._debt("2000000")
        DebtPayment.objects.create(
            debt=debt, amount=Decimal("2000000"), paid_on=self.today
        )
        self.assertTrue(debt.is_settled)
        self.assertEqual(debt.remaining_amount, Decimal("0"))
        self.assertEqual(debt.paid_percent, Decimal("100.00"))
        self.assertEqual(debt.status, DebtStatus.SETTLED)

    def test_remaining_never_negative(self):
        """Even if the data is inconsistent, the remainder must not go below 0."""
        debt = self._debt("1000000")
        DebtPayment.objects.create(
            debt=debt, amount=Decimal("1000000"), paid_on=self.today
        )
        self.assertGreaterEqual(debt.remaining_amount, Decimal("0"))

    def test_status_is_active_before_any_payment(self):
        debt = self._debt("1000000", due_on=self.today + dt.timedelta(days=10))
        self.assertEqual(debt.status, DebtStatus.ACTIVE)

    def test_status_is_partial_after_partial_payment(self):
        debt = self._debt("1000000", due_on=self.today + dt.timedelta(days=10))
        DebtPayment.objects.create(
            debt=debt, amount=Decimal("400000"), paid_on=self.today
        )
        self.assertEqual(debt.status, DebtStatus.PARTIAL)

    def test_status_is_overdue_past_due_date(self):
        debt = self._debt("1000000", due_on=self.today - dt.timedelta(days=3))
        self.assertTrue(debt.is_overdue)
        self.assertEqual(debt.status, DebtStatus.OVERDUE)
        self.assertEqual(debt.days_until_due, -3)

    def test_settled_debt_is_never_overdue(self):
        """A debt paid late but paid must read as settled, not overdue."""
        debt = self._debt("1000000", due_on=self.today - dt.timedelta(days=30))
        DebtPayment.objects.create(
            debt=debt, amount=Decimal("1000000"), paid_on=self.today
        )
        self.assertFalse(debt.is_overdue)
        self.assertEqual(debt.status, DebtStatus.SETTLED)

    def test_days_until_due_positive_before_due(self):
        debt = self._debt("1000000", due_on=self.today + dt.timedelta(days=7))
        self.assertEqual(debt.days_until_due, 7)

    def test_receivable_direction_is_recorded(self):
        debt = self._debt("4000000", direction=DebtDirection.RECEIVABLE)
        self.assertEqual(debt.direction, DebtDirection.RECEIVABLE)


class DebtOverpaymentTests(TestCase):
    """A payment that exceeds the remainder must be rejected, not truncated."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="overpay@test.ir", password="StrongPass!234"
        )
        self.today = dt.date.today()
        self.debt = Debt.objects.create(
            user=self.user,
            direction=DebtDirection.PAYABLE,
            counterparty="بانک تست",
            principal=Decimal("5000000"),
            issued_on=self.today - dt.timedelta(days=30),
            due_on=self.today + dt.timedelta(days=30),
        )
        DebtPayment.objects.create(
            debt=self.debt, amount=Decimal("1000000"), paid_on=self.today
        )

    def _payment_serializer(self, amount):
        # The view passes the debt through serializer context, because the
        # remaining balance is derived from the debt (and its other payments)
        # rather than supplied by the client.
        return DebtPaymentWriteSerializer(
            data={"amount": amount, "paid_on": self.today.isoformat()},
            context={"debt": self.debt, "request": None},
        )

    def test_overpayment_is_rejected(self):
        serializer = self._payment_serializer("5000000")
        self.assertFalse(serializer.is_valid())
        self.assertIn("amount", serializer.errors)

    def test_exact_remainder_is_accepted(self):
        serializer = self._payment_serializer("4000000")
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_one_unit_over_the_remainder_is_rejected(self):
        serializer = self._payment_serializer("4000000.01")
        self.assertFalse(serializer.is_valid())
        self.assertIn("amount", serializer.errors)

    def test_zero_and_negative_payments_are_rejected(self):
        for amount in ("0", "-500000"):
            serializer = self._payment_serializer(amount)
            self.assertFalse(serializer.is_valid(), f"{amount} should be rejected")

    def test_payment_does_not_delete_or_mutate_earlier_payments(self):
        serializer = self._payment_serializer("1000000")
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        self.assertEqual(DebtPayment.objects.filter(debt=self.debt).count(), 2)
        self.assertEqual(self.debt.paid_amount, Decimal("2000000"))

    def test_near_future_dated_payment_is_accepted(self):
        """A payment scheduled slightly ahead is legitimate.

        `paid_on` is the date the user attributes the payment to, which for a
        standing order or a post-dated cheque is in the near future. Slightly
        loose on the horizon so a user ahead of the server's timezone is not
        blocked when recording something dated "today" locally.
        """
        serializer = DebtPaymentWriteSerializer(
            data={
                "amount": "1000000",
                "paid_on": (self.today + dt.timedelta(days=30)).isoformat(),
            },
            context={"debt": self.debt, "request": None},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_far_future_dated_payment_is_rejected(self):
        """Far enough ahead it is a typo — a mistyped year, most likely."""
        serializer = DebtPaymentWriteSerializer(
            data={
                "amount": "1000000",
                "paid_on": (self.today + dt.timedelta(days=FUTURE_HORIZON_DAYS + 30)).isoformat(),
            },
            context={"debt": self.debt, "request": None},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("paid_on", serializer.errors)


class DebtTotalsTests(TestCase):
    """Summary totals must separate what I owe from what I am owed."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="totals@test.ir", password="StrongPass!234"
        )
        self.today = dt.date.today()

    def _debt(self, direction, principal, paid=0, due_offset=10):
        debt = Debt.objects.create(
            user=self.user,
            direction=direction,
            counterparty="طرف حساب",
            principal=Decimal(principal),
            issued_on=self.today - dt.timedelta(days=90),
            due_on=self.today + dt.timedelta(days=due_offset),
        )
        if paid:
            DebtPayment.objects.create(
                debt=debt, amount=Decimal(paid), paid_on=self.today
            )
        return debt

    def test_payables_and_receivables_are_reported_separately(self):
        from apps.debts.serializers import debt_totals

        self._debt(DebtDirection.PAYABLE, "10000000", paid="3000000")
        self._debt(DebtDirection.PAYABLE, "5000000")
        self._debt(DebtDirection.RECEIVABLE, "2000000", paid="500000")

        totals = debt_totals(self.user)

        # Totals are serialized as quantized decimal strings so the client
        # never re-derives money from a JSON number.
        # Owed: 7_000_000 + 5_000_000
        self.assertEqual(totals["payable_remaining"], "12000000.00")
        # Owed to me: 1_500_000
        self.assertEqual(totals["receivable_remaining"], "1500000.00")
        self.assertEqual(totals["payable_total"], "15000000.00")
        self.assertEqual(totals["receivable_total"], "2000000.00")

    def test_receivables_do_not_offset_payables(self):
        from apps.debts.serializers import debt_totals

        self._debt(DebtDirection.PAYABLE, "10000000")
        self._debt(DebtDirection.RECEIVABLE, "8000000")

        totals = debt_totals(self.user)
        # Two independent figures, not a single netted one.
        self.assertEqual(totals["payable_remaining"], "10000000.00")
        self.assertEqual(totals["receivable_remaining"], "8000000.00")

    def test_net_position_is_receivable_minus_payable(self):
        from apps.debts.serializers import debt_totals

        self._debt(DebtDirection.PAYABLE, "10000000")
        self._debt(DebtDirection.RECEIVABLE, "3000000")

        totals = debt_totals(self.user)
        # I owe more than I am owed, so the net position is negative.
        self.assertEqual(totals["net_position"], "-7000000.00")

    def test_overdue_totals_count_only_overdue(self):
        from apps.debts.serializers import debt_totals

        self._debt(DebtDirection.PAYABLE, "3000000", due_offset=-5)
        self._debt(DebtDirection.PAYABLE, "4000000", due_offset=20)

        totals = debt_totals(self.user)
        self.assertEqual(totals["overdue_count"], 1)
        self.assertEqual(totals["overdue_amount"], "3000000.00")

    def test_settled_debts_are_excluded_from_remaining(self):
        from apps.debts.serializers import debt_totals

        self._debt(DebtDirection.PAYABLE, "3000000", paid="3000000")
        self._debt(DebtDirection.PAYABLE, "1000000")

        totals = debt_totals(self.user)
        self.assertEqual(totals["payable_remaining"], "1000000.00")
        self.assertEqual(totals["settled_count"], 1)
        self.assertEqual(totals["open_count"], 1)
        self.assertEqual(totals["total_count"], 2)


class DebtIsolationTests(TestCase):
    """One user must never see, edit, or pay another user's debt."""

    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner@test.ir", password="StrongPass!234"
        )
        self.other = User.objects.create_user(
            email="other@test.ir", password="StrongPass!234"
        )
        self.today = dt.date.today()
        self.debt = Debt.objects.create(
            user=self.owner,
            direction=DebtDirection.PAYABLE,
            counterparty="بانک من",
            principal=Decimal("9000000"),
            issued_on=self.today - dt.timedelta(days=30),
            due_on=self.today + dt.timedelta(days=30),
        )

    def test_debt_is_not_visible_to_other_user(self):
        self.assertEqual(Debt.objects.filter(user=self.other).count(), 0)
        self.assertEqual(Debt.objects.for_user(self.other).count(), 0)

    def test_owner_queryset_returns_the_debt(self):
        self.assertEqual(Debt.objects.for_user(self.owner).count(), 1)

    def test_other_user_cannot_pay_someone_elses_debt(self):
        """A debt outside the caller's queryset must be unreachable.

        The view resolves the debt through ``Debt.objects.for_user(request.user)``,
        so scoping the queryset is what prevents cross-account payment. This
        asserts that scope directly.
        """
        self.assertFalse(
            Debt.objects.for_user(self.other).filter(pk=self.debt.pk).exists()
        )
        self.assertTrue(
            Debt.objects.for_user(self.owner).filter(pk=self.debt.pk).exists()
        )

    def test_payments_are_scoped_through_the_debt_owner(self):
        DebtPayment.objects.create(
            debt=self.debt, amount=Decimal("1000000"), paid_on=self.today
        )
        self.assertEqual(DebtPayment.objects.filter(debt__user=self.other).count(), 0)
        self.assertEqual(DebtPayment.objects.filter(debt__user=self.owner).count(), 1)


class DebtDisplayTests(TestCase):
    """Persian display strings must be present and Jalali, never Gregorian."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="display@test.ir", password="StrongPass!234"
        )
        self.today = dt.date.today()
        self.debt = Debt.objects.create(
            user=self.user,
            direction=DebtDirection.PAYABLE,
            counterparty="فروشگاه",
            principal=Decimal("7500000"),
            issued_on=self.today - dt.timedelta(days=40),
            due_on=self.today + dt.timedelta(days=2),
        )

    def test_due_date_renders_in_jalali(self):
        from apps.debts.serializers import DebtSerializer

        data = DebtSerializer(self.debt).data
        self.assertIn("due_on_display", data)
        # The Jalali year for the current era is 14xx; a Gregorian 20xx year
        # appearing here would mean the date leaked through unconverted.
        self.assertNotIn("2026", str(data["due_on_display"]))
        self.assertNotIn("۲۰۲۶", str(data["due_on_display"]))

    def test_amounts_render_with_persian_separator(self):
        from apps.debts.serializers import DebtSerializer

        data = DebtSerializer(self.debt).data
        self.assertIn("٬", data["principal_display"])

    def test_remaining_display_matches_principal_when_unpaid(self):
        from apps.debts.serializers import DebtSerializer

        data = DebtSerializer(self.debt).data
        self.assertEqual(data["paid_amount"], "0.00")
        self.assertEqual(data["remaining_amount"], "7500000.00")

    def test_due_relative_reads_naturally(self):
        from apps.debts.serializers import DebtSerializer

        data = DebtSerializer(self.debt).data
        self.assertIn("مانده", data["due_relative"])

    def test_overdue_relative_says_how_long_ago(self):
        overdue = Debt.objects.create(
            user=self.user,
            direction=DebtDirection.PAYABLE,
            counterparty="فروشگاه",
            principal=Decimal("1000000"),
            issued_on=self.today - dt.timedelta(days=40),
            due_on=self.today - dt.timedelta(days=5),
        )
        from apps.debts.serializers import DebtSerializer

        data = DebtSerializer(overdue).data
        self.assertIn("گذشته", data["due_relative"])

    def test_status_label_is_persian(self):
        from apps.debts.serializers import DebtSerializer

        data = DebtSerializer(self.debt).data
        self.assertTrue(any("\u0600" <= ch <= "\u06ff" for ch in data["status_label"]))
