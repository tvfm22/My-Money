"""Tests for money handling.

The point of these tests is the invariant that matters most in a finance app:
amounts must be exact. Anything that would let a float in, or silently drop
precision, is a bug worth catching here rather than in a user's balance.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import SimpleTestCase

from apps.core.money import (
    clamp,
    percentage,
    progress_ratio,
    quantize_money,
    safe_divide,
    sum_money,
    to_decimal,
)


class ToDecimalTests(SimpleTestCase):
    def test_float_is_coerced_via_str(self):
        """0.1 must become exactly 0.1, not the binary approximation."""
        self.assertEqual(to_decimal(0.1), Decimal("0.1"))
        self.assertEqual(to_decimal(0.3), Decimal("0.3"))
        # The naive Decimal(0.1) route would fail this.
        self.assertNotEqual(to_decimal(0.1), Decimal(0.1))

    def test_none_becomes_zero(self):
        self.assertEqual(to_decimal(None), Decimal("0"))

    def test_string_is_exact(self):
        self.assertEqual(to_decimal("1234.56"), Decimal("1234.56"))

    def test_int(self):
        self.assertEqual(to_decimal(500), Decimal("500"))

    def test_invalid_raises_value_error(self):
        with self.assertRaises(ValueError):
            to_decimal("abc")

    def test_returned_value_is_decimal(self):
        for value in [1, 1.5, "2.5", Decimal("3"), None]:
            with self.subTest(value=value):
                self.assertIsInstance(to_decimal(value), Decimal)


class QuantizeMoneyTests(SimpleTestCase):
    def test_rounds_half_up_not_bankers(self):
        """0.005 must round up to 0.01, not to the even 0.00."""
        self.assertEqual(quantize_money("0.005"), Decimal("0.01"))
        self.assertEqual(quantize_money("0.015"), Decimal("0.02"))

    def test_always_two_decimal_places(self):
        self.assertEqual(quantize_money(1000), Decimal("1000.00"))
        self.assertEqual(quantize_money("1000.5"), Decimal("1000.50"))

    def test_idempotent(self):
        once = quantize_money("123.456")
        self.assertEqual(quantize_money(once), once)


class SumMoneyTests(SimpleTestCase):
    def test_sum_is_exact(self):
        # The classic float failure: 0.1 + 0.2 != 0.3
        self.assertEqual(sum_money(["0.1", "0.2"]), Decimal("0.30"))

    def test_empty_is_zero_decimal(self):
        result = sum_money([])
        self.assertEqual(result, Decimal("0.00"))
        self.assertIsInstance(result, Decimal)

    def test_many_small_amounts_do_not_drift(self):
        """A thousand 0.01 additions must land exactly on 10.00."""
        total = sum_money(["0.01"] * 1000)
        self.assertEqual(total, Decimal("10.00"))

    def test_large_toman_amounts(self):
        total = sum_money([16_000_000, 4_500_000, "250000.50"])
        self.assertEqual(total, Decimal("20750000.50"))


class SafeDivideTests(SimpleTestCase):
    def test_division(self):
        self.assertEqual(safe_divide(10, 4), Decimal("2.5"))

    def test_zero_denominator_returns_default(self):
        """A user with no budget must not cause a crash."""
        self.assertEqual(safe_divide(100, 0), Decimal("0.00"))

    def test_zero_denominator_custom_default(self):
        self.assertEqual(safe_divide(100, 0, default=Decimal("-1")), Decimal("-1"))

    def test_zero_numerator(self):
        self.assertEqual(safe_divide(0, 100), Decimal("0"))


class PercentageTests(SimpleTestCase):
    def test_basic_percentage(self):
        self.assertEqual(percentage(65, 100), Decimal("65.00"))
        self.assertEqual(percentage(1, 2), Decimal("50.00"))

    def test_budget_example(self):
        """۱۶,۰۰۰,۰۰۰ spent against a ۲۰,۰۰۰,۰۰۰ budget is 80%."""
        self.assertEqual(percentage(16_000_000, 20_000_000), Decimal("80.00"))

    def test_over_budget_exceeds_100(self):
        """Overspending is real information and must not be silently capped."""
        self.assertEqual(percentage(130, 100), Decimal("130.00"))

    def test_zero_budget_is_zero_not_error(self):
        self.assertEqual(percentage(500, 0), Decimal("0.00"))

    def test_result_is_quantized(self):
        result = percentage(1, 3)
        self.assertEqual(result, Decimal("33.33"))


class ProgressRatioTests(SimpleTestCase):
    def test_normal(self):
        self.assertEqual(progress_ratio(50, 100), Decimal("0.5"))

    def test_clamped_at_one(self):
        """Progress bars take a 0..1 ratio; 130% must clamp to full."""
        self.assertEqual(progress_ratio(130, 100), Decimal("1"))

    def test_clamped_at_zero(self):
        self.assertEqual(progress_ratio(-10, 100), Decimal("0"))

    def test_zero_whole(self):
        self.assertEqual(progress_ratio(10, 0), Decimal("0"))


class ClampTests(SimpleTestCase):
    def test_within_range(self):
        self.assertEqual(clamp(Decimal("5"), Decimal("0"), Decimal("10")), Decimal("5"))

    def test_below_range(self):
        self.assertEqual(clamp(Decimal("-5"), Decimal("0"), Decimal("10")), Decimal("0"))

    def test_above_range(self):
        self.assertEqual(clamp(Decimal("50"), Decimal("0"), Decimal("10")), Decimal("10"))
