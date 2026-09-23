"""Tests for the shared amount parser in ``apps.sms.amounts``.

Every money field in the parser goes through this module, so the rules pinned
here — rial÷10, unit words, identifiers that look like money — apply to the
transaction amount *and* to the balance at once.
"""

from decimal import Decimal

from django.test import SimpleTestCase

from apps.sms.amounts import (
    DEFAULT_WINDOW,
    RIAL,
    TOMAN,
    UNIT_UNKNOWN,
    amount_near_label,
    candidates,
    find_amounts,
    parse_amount_text,
    to_toman,
)


class FindAmountsTests(SimpleTestCase):
    def test_grouped_rial_amount(self):
        (amount,) = find_amounts("مبلغ 1,500,000 ریال")
        self.assertEqual(amount.value, Decimal("1500000"))
        self.assertEqual(amount.unit, RIAL)
        self.assertFalse(amount.unit_assumed)

    def test_unit_word_variants(self):
        self.assertEqual(find_amounts("500 تومن")[0].unit, TOMAN)
        self.assertEqual(find_amounts("1,200 IRR")[0].unit, RIAL)
        self.assertEqual(find_amounts("300 TOMAN")[0].unit, TOMAN)

    def test_missing_unit_is_recorded_as_assumed_rial(self):
        (amount,) = find_amounts("مبلغ 250000")
        self.assertEqual(amount.unit, UNIT_UNKNOWN)
        self.assertTrue(amount.unit_assumed)
        self.assertEqual(amount.toman, Decimal("25000.00"))

    def test_decimal_part_is_kept(self):
        (amount,) = find_amounts("1,500,000.50 ریال")
        self.assertEqual(amount.value, Decimal("1500000.50"))

    def test_signed_amount(self):
        (amount,) = find_amounts("-1,100,000")
        self.assertEqual(amount.sign, "-")

    def test_long_digit_runs_are_identifiers_not_money(self):
        # 16 digits is a card number, 9 an account/reference code — never money.
        self.assertEqual(find_amounts("6037991234567890"), [])
        self.assertEqual(find_amounts("123456789"), [])

    def test_identifier_prefixes_are_not_money(self):
        self.assertEqual(find_amounts("کارت 7284"), [])
        self.assertEqual(find_amounts("کد رهگیری 45812"), [])

    def test_date_and_clock_components_are_not_money(self):
        self.assertEqual(find_amounts("1405/07/01"), [])
        self.assertEqual(find_amounts("14:30"), [])


class ToTomanTests(SimpleTestCase):
    def test_rial_divides_by_ten(self):
        self.assertEqual(to_toman(Decimal("488152"), RIAL), Decimal("48815.20"))

    def test_toman_passes_through(self):
        self.assertEqual(to_toman(Decimal("25000"), TOMAN), Decimal("25000.00"))

    def test_unknown_unit_is_assumed_rial(self):
        self.assertEqual(to_toman(Decimal("1000"), UNIT_UNKNOWN), Decimal("100.00"))

    def test_match_toman_property_uses_the_unit(self):
        self.assertEqual(find_amounts("مبلغ 200,000 ریال")[0].toman, Decimal("20000.00"))
        self.assertEqual(find_amounts("مبلغ 20,000 تومان")[0].toman, Decimal("20000.00"))


class CandidatesTests(SimpleTestCase):
    def test_tiny_unsigned_figure_is_dropped(self):
        self.assertEqual(candidates(find_amounts("50 ریال")), [])

    def test_signed_figure_is_kept_even_when_small(self):
        # The sign is direction information (Bankino) — never discarded.
        self.assertEqual(len(candidates(find_amounts("-500"))), 1)

    def test_normal_amount_survives(self):
        self.assertEqual(len(candidates(find_amounts("مبلغ 200,000 ریال"))), 1)


class NearLabelTests(SimpleTestCase):
    def _label_span(self, text, needle):
        start = text.index(needle)
        return start, start + len(needle)

    def test_figure_after_the_label_wins(self):
        text = "مانده 488,152 ریال"
        label_start, label_end = self._label_span(text, "مانده")
        match = amount_near_label(label_start, label_end, find_amounts(text))
        self.assertEqual(match.value, Decimal("488152"))

    def test_figure_before_the_label_when_allowed(self):
        # blu Bank's figure-first shape — this is the direction-phrase case.
        text = "2,500,000 ریال از حساب شما پرید"
        label_start, label_end = self._label_span(text, "از حساب شما پرید")
        match = amount_near_label(
            label_start, label_end, find_amounts(text), allow_before=True
        )
        self.assertEqual(match.value, Decimal("2500000"))

    def test_balance_never_takes_the_figure_before_its_label(self):
        text = "مبلغ 200,000 ریال کسر گردید. موجودی"
        label_start, label_end = self._label_span(text, "موجودی")
        match = amount_near_label(
            label_start, label_end, find_amounts(text), allow_before=False
        )
        self.assertIsNone(match)

    def test_claimed_span_is_not_reused(self):
        text = "مبلغ 100,000 ریال مانده 488,152 ریال"
        amounts = find_amounts(text)
        first = min(amounts, key=lambda amount: amount.start)
        label_start, label_end = self._label_span(text, "مانده")
        match = amount_near_label(
            label_start,
            label_end,
            amounts,
            exclude=((first.start, first.end),),
            allow_before=False,
        )
        self.assertEqual(match.value, Decimal("488152"))

    def test_figure_beyond_the_window_is_not_attached(self):
        text = "مانده" + " " * (DEFAULT_WINDOW + 1) + "488,152 ریال"
        label_start, label_end = self._label_span(text, "مانده")
        match = amount_near_label(label_start, label_end, find_amounts(text))
        self.assertIsNone(match)


class ParseAmountTextTests(SimpleTestCase):
    def test_plain_and_grouped(self):
        self.assertEqual(parse_amount_text("1,500,000"), Decimal("1500000"))
        self.assertEqual(parse_amount_text(" 2500 "), Decimal("2500"))

    def test_garbage_is_none(self):
        self.assertIsNone(parse_amount_text(""))
        self.assertIsNone(parse_amount_text("abc"))