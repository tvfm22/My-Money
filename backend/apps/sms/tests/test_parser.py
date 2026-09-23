"""Parser tests.

The cases pinned down here are the ones the parser was specified against, plus
the two properties that are easy to lose in a refactor and impossible to notice:

*   **A balance is attached by proximity to its label, never by position.** The
    same pair of figures is parsed in both orders and must land in the same
    fields either way. A "first number is the amount" implementation passes the
    common case and fails this one.
*   **A message with no balance produces ``None``, and loses only the balance's
    own weight.** An implementation that defaults to zero, or that treats a
    missing balance as a failed parse, fails here.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.test import TestCase

from apps.sms.normalize import fingerprint, normalize_text
from apps.sms.parser import LOW_CONFIDENCE, parse_sms

# --------------------------------------------------------------------------
# Messages used by more than one test
# --------------------------------------------------------------------------

# The withdrawal sentence Sepah, Keshavarzi, Maskan and Saman all use, with the
# balance on its own line.
WITHDRAWAL_MULTILINE = "از حساب شما مبلغ 500,000 ریال کسر گردید.\nموجودی: 1,500,000 ریال"

# The mirror sentence for a deposit.
DEPOSIT_MULTILINE = "به حساب شما مبلغ 1,500,000 ریال واریز گردید.\nموجودی: 2,500,000 ریال"


class RequiredVariantTests(TestCase):
    """The SMS variants the task named, one test each."""

    def test_withdrawal_with_balance_on_a_separate_line(self):
        parsed = parse_sms(WITHDRAWAL_MULTILINE)

        self.assertTrue(parsed.is_transaction)
        self.assertEqual(parsed.direction, "expense")
        self.assertEqual(parsed.amount_toman, Decimal("50000.00"))
        self.assertEqual(parsed.balance_after, Decimal("150000.00"))
        self.assertEqual(parsed.balance_label, "موجودی")

    def test_deposit_with_balance_on_a_separate_line(self):
        parsed = parse_sms(DEPOSIT_MULTILINE)

        self.assertEqual(parsed.direction, "income")
        self.assertEqual(parsed.amount_toman, Decimal("150000.00"))
        self.assertEqual(parsed.balance_after, Decimal("250000.00"))

    def test_kasr_shod_instead_of_kasr_gardid(self):
        """«کسر شد» is the shortened form of the same sentence."""
        parsed = parse_sms("از حساب شما مبلغ 250,000 ریال کسر شد. موجودی: 750,000 ریال")

        self.assertEqual(parsed.direction, "expense")
        self.assertEqual(parsed.direction_pattern, "debit_sentence_kasr")
        self.assertEqual(parsed.amount_toman, Decimal("25000.00"))
        self.assertEqual(parsed.balance_after, Decimal("75000.00"))

    def test_mande_hesab_instead_of_mojoodi(self):
        """«مانده حساب» is a balance label even though the word differs."""
        parsed = parse_sms(
            "از حساب شما مبلغ 300,000 ریال کسر گردید. مانده حساب: 1,200,000 ریال"
        )

        self.assertEqual(parsed.amount_toman, Decimal("30000.00"))
        self.assertEqual(parsed.balance_after, Decimal("120000.00"))
        self.assertEqual(parsed.balance_label, "مانده حساب")

    def test_no_balance_at_all_is_null_not_zero(self):
        """The absence of a balance is not an error and not a zero."""
        parsed = parse_sms("خرید با کارت ****7284 مبلغ 450,000 ریال\n1405/06/15")

        self.assertIsNone(parsed.balance_after)
        # Not zero: a zero balance reads as "the account is empty", which is a
        # different — and false — statement.
        self.assertNotEqual(parsed.balance_after, Decimal("0"))
        self.assertIsNone(parsed.to_dict()["balance_after"])

    def test_missing_balance_costs_only_the_balance_weight(self):
        """Compare the same message with and without a balance line.

        The only difference must be the balance's 0.10 weight: direction, amount
        and date are read identically in both. This is the assertion that fails
        if someone makes a missing balance drop the item out of the review queue.
        """
        without = parse_sms("خرید با کارت ****7284 مبلغ 450,000 ریال\n1405/06/15")
        with_balance = parse_sms(
            "خرید با کارت ****7284 مبلغ 450,000 ریال\nموجودی: 1,450,000 ریال\n1405/06/15"
        )

        self.assertEqual(with_balance.confidence - without.confidence, Decimal("0.100"))
        # Still comfortably usable, and every other field is unaffected.
        self.assertGreaterEqual(without.confidence, Decimal("0.75"))
        self.assertGreaterEqual(without.confidence, LOW_CONFIDENCE)
        self.assertEqual(without.field_confidence["balance"], Decimal("0.000"))
        self.assertEqual(without.field_confidence["amount"], Decimal("1.000"))
        self.assertEqual(without.field_confidence["direction"], Decimal("0.850"))

    def test_similar_amount_and_balance_are_attached_by_label_proximity(self):
        """Both figures have the same number of digits — and swap nothing."""
        parsed = parse_sms(
            "از حساب شما مبلغ 1,234,567 ریال کسر گردید. موجودی: 9,876,543 ریال"
        )

        self.assertEqual(parsed.amount_toman, Decimal("123456.70"))
        self.assertEqual(parsed.balance_after, Decimal("987654.30"))
        self.assertNotEqual(parsed.amount_toman, parsed.balance_after)

    def test_balance_first_does_not_become_the_amount(self):
        """The same figures with the lines swapped must not swap fields.

        This is the case a positional implementation cannot pass: the balance is
        printed *before* the amount, so "first number wins" would put 987,654 in
        the amount and 123,456 in the balance.
        """
        parsed = parse_sms(
            "موجودی: 9,876,543 ریال\nاز حساب شما مبلغ 1,234,567 ریال کسر گردید."
        )

        self.assertEqual(parsed.amount_toman, Decimal("123456.70"))
        self.assertEqual(parsed.balance_after, Decimal("987654.30"))
        self.assertEqual(parsed.direction, "expense")


# --------------------------------------------------------------------------
# Direction table
# --------------------------------------------------------------------------


class DirectionTableTests(TestCase):
    def test_sentence_pattern_beats_a_bare_keyword_in_the_same_message(self):
        """A message containing both must resolve by the more specific rule.

        `برداشت پول` is a debit keyword and `به حساب شما واریز گردید` is a credit
        sentence. The sentence is more specific, so it wins — which is only true
        because the table is ordered rather than a dict.
        """
        parsed = parse_sms(
            "برداشت پول از حساب شما انجام شد و مبلغ 900,000 ریال به حساب شما واریز گردید."
        )

        self.assertEqual(parsed.direction, "income")
        self.assertEqual(parsed.direction_pattern, "credit_sentence_variz")
        self.assertEqual(parsed.direction_kind, "phrase")

    def test_withdrawal_sentence_beats_the_variz_keyword(self):
        parsed = parse_sms(
            "واریزهای قبلی لحاظ شده است. از حساب شما مبلغ 700,000 ریال کسر گردید."
        )

        self.assertEqual(parsed.direction, "expense")
        self.assertEqual(parsed.direction_pattern, "debit_sentence_kasr")

    def test_keyword_fallback_when_no_sentence_matches(self):
        parsed = parse_sms("خرید مبلغ 300,000 ریال")
        self.assertEqual(parsed.direction, "expense")
        self.assertEqual(parsed.direction_kind, "keyword")

    def test_accounting_tags(self):
        credited = parse_sms("حساب شما بستانکار شد. مبلغ 2,000,000 ریال. مانده: 4,000,000 ریال")
        debited = parse_sms("حساب شما بدهکار شد. مبلغ 2,000,000 ریال. مانده: 4,000,000 ریال")

        self.assertEqual(credited.direction, "income")
        self.assertEqual(credited.direction_pattern, "credit_bestankar")
        self.assertEqual(debited.direction, "expense")
        self.assertEqual(debited.direction_pattern, "debit_bedehkar")

    def test_outgoing_transfer_is_an_expense(self):
        parsed = parse_sms("انتقال به حساب آقای رضایی مبلغ 1,000,000 ریال. مانده: 500,000 ریال")

        self.assertEqual(parsed.direction, "expense")
        self.assertEqual(parsed.amount_toman, Decimal("100000.00"))

    def test_blu_bank_colloquial_sentences(self):
        withdrawal = parse_sms(
            "بلو\nبرداشت پول\nمانی عزیز، 2,500,000 ریال از حساب شما پرید.\n"
            "موجودی: 488,152 ریال\n۷:۲۸\n۱۴۰۵.۰۳.۲۲"
        )
        deposit = parse_sms("بلو\nواریز پول\nمانی عزیز، 70,000,000 ریال به حساب شما نشست.")

        self.assertEqual(withdrawal.direction, "expense")
        self.assertEqual(withdrawal.direction_pattern, "debit_blu_perid")
        self.assertEqual(withdrawal.amount_toman, Decimal("250000.00"))
        self.assertEqual(withdrawal.balance_after, Decimal("48815.20"))
        self.assertEqual(withdrawal.occurred_on, dt.date(2026, 6, 12))

        self.assertEqual(deposit.direction, "income")
        self.assertEqual(deposit.direction_pattern, "credit_blu_neshast")
        self.assertEqual(deposit.amount_toman, Decimal("7000000.00"))

    def test_melli_phrases_the_deposit_the_other_way_round(self):
        parsed = parse_sms(
            "مبلغ 1,500,000 ریال واریز به حساب شما انجام شد. مانده: 2,500,000 ریال"
        )

        self.assertEqual(parsed.direction, "income")
        self.assertEqual(parsed.direction_pattern, "credit_sentence_variz_be_hesab")
        self.assertEqual(parsed.amount_toman, Decimal("150000.00"))
        self.assertEqual(parsed.balance_after, Decimal("250000.00"))

    def test_signed_amount_decides_direction_as_a_last_resort(self):
        """Bankino states direction only through the sign."""
        parsed = parse_sms("بانک خاورمیانه\n-1,100,000\nمانده 17,712,600\n1405/03/22")

        self.assertEqual(parsed.direction, "expense")
        self.assertEqual(parsed.direction_kind, "sign")
        self.assertEqual(parsed.amount_toman, Decimal("110000.00"))
        self.assertEqual(parsed.balance_after, Decimal("1771260.00"))

    def test_unknown_direction_is_reported_not_guessed(self):
        parsed = parse_sms("مبلغ 500,000 ریال\nموجودی: 900,000 ریال")

        self.assertIsNone(parsed.direction)
        self.assertFalse(parsed.is_usable)
        self.assertIn("جهت تراکنش از متن پیامک مشخص نشد.", parsed.warnings)
        # The amount is still read: the user only has to pick a direction.
        self.assertEqual(parsed.amount_toman, Decimal("50000.00"))


# --------------------------------------------------------------------------
# Balance labels
# --------------------------------------------------------------------------


class BalanceLabelTests(TestCase):
    """Every required label spelling maps to the one field, `balance_after`."""

    def test_mojoodi_feli(self):
        parsed = parse_sms("خرید مبلغ 200,000 ریال. موجودی فعلی: 1,100,000 ریال")

        self.assertEqual(parsed.balance_after, Decimal("110000.00"))
        self.assertEqual(parsed.balance_label, "موجودی فعلی")

    def test_mande_ghabele_bardasht(self):
        parsed = parse_sms("برداشت مبلغ 100,000 ریال. مانده قابل برداشت: 900,000 ریال")

        self.assertEqual(parsed.balance_after, Decimal("90000.00"))
        self.assertEqual(parsed.balance_label, "مانده قابل برداشت")

    def test_label_present_but_no_figure_means_no_balance(self):
        """A dangling label must not pull in the transaction amount."""
        parsed = parse_sms("از حساب شما مبلغ 200,000 ریال کسر گردید. موجودی قابل برداشت")

        self.assertIsNone(parsed.balance_after)
        self.assertEqual(parsed.amount_toman, Decimal("20000.00"))

    def test_first_label_with_a_figure_wins(self):
        """Two labels in one message resolve deterministically, in text order."""
        parsed = parse_sms(
            "موجودی: 1,000,000 ریال\nبرداشت مبلغ 200,000 ریال. مانده حساب: 800,000 ریال"
        )

        self.assertEqual(parsed.balance_after, Decimal("100000.00"))
        self.assertEqual(parsed.amount_toman, Decimal("20000.00"))

    def test_the_amount_is_never_reused_as_the_balance(self):
        """With one figure and two labels, no field may steal the other's number."""
        parsed = parse_sms("برداشت 500,000 ریال. موجودی:")

        self.assertEqual(parsed.amount_toman, Decimal("50000.00"))
        self.assertIsNone(parsed.balance_after)


# --------------------------------------------------------------------------
# Typography
# --------------------------------------------------------------------------


class TypographyTests(TestCase):
    def test_normalize_text_canonicalizes_every_variant(self):
        self.assertEqual(
            normalize_text("موجودي: ۴۸۸,۱۵۲ ريال"),
            "موجودی: 488,152 ریال",
        )
        # U+066C and U+066B are the Persian grouping/radix glyphs.
        self.assertEqual(
            normalize_text("موجودی: ۱٬۵۰۰٬۰۰۰\u066b۵ ریال"),
            "موجودی: 1,500,000.5 ریال",
        )

    def test_persian_digits_and_persian_separators(self):
        parsed = parse_sms("از حساب شما مبلغ ۵۰۰٬۰۰۰ ریال کسر گردید. موجودی: ۱٬۵۰۰٬۰۰۰ ریال")

        self.assertEqual(parsed.amount_toman, Decimal("50000.00"))
        self.assertEqual(parsed.balance_after, Decimal("150000.00"))

    def test_arabic_kaf_and_yeh_are_matched(self):
        """`كسر گردید` and `موجودي` are what many phone keyboards produce."""
        arabic = "از حساب شما مبلغ 300,000 ریال كسر گردید. موجودي حساب: 900,000 ریال"
        parsed = parse_sms(arabic)

        self.assertEqual(parsed.direction, "expense")
        self.assertEqual(parsed.normalized, normalize_text(arabic))
        self.assertNotIn("ي", parsed.normalized)
        self.assertEqual(parsed.amount_toman, Decimal("30000.00"))
        self.assertEqual(parsed.balance_after, Decimal("90000.00"))
        self.assertEqual(parsed.balance_label, "موجودی حساب")

    def test_arabic_indic_digits(self):
        parsed = parse_sms("برداشت مبلغ ٣٠٠,٠٠٠ ریال. مانده: ٩٠٠,٠٠٠ ریال")

        self.assertEqual(parsed.amount_toman, Decimal("30000.00"))
        self.assertEqual(parsed.balance_after, Decimal("90000.00"))

    def test_fingerprint_ignores_digit_glyphs(self):
        """The same message pasted from two phones must hash the same."""
        latin = parse_sms("خرید مبلغ 300,000 ریال. مانده: 900,000 ریال")
        persian = parse_sms("خرید مبلغ ۳۰۰٬۰۰۰ ریال. مانده: ۹۰۰٬۰۰۰ ریال")

        self.assertEqual(latin.fingerprint, persian.fingerprint)
        self.assertEqual(latin.fingerprint, fingerprint("خرید مبلغ 300,000 ریال. مانده: 900,000 ریال"))
        self.assertNotEqual(latin.fingerprint, parse_sms("خرید مبلغ 301,000 ریال").fingerprint)


# --------------------------------------------------------------------------
# Units
# --------------------------------------------------------------------------


class UnitTests(TestCase):
    """The app stores Toman; most banks quote Rial."""

    def test_rial_is_converted_at_ten_to_one(self):
        parsed = parse_sms("خرید مبلغ 1,000,000 ریال. مانده: 3,000,000 ریال")

        self.assertEqual(parsed.amount_toman, Decimal("100000.00"))
        self.assertEqual(parsed.balance_after, Decimal("300000.00"))
        self.assertEqual(parsed.amount_unit, "rial")
        self.assertFalse(parsed.amount_was_assumed)

    def test_toman_is_kept_as_written(self):
        parsed = parse_sms("خرید مبلغ 450,000 تومان. موجودی: 1,000,000 تومان")

        self.assertEqual(parsed.amount_toman, Decimal("450000.00"))
        self.assertEqual(parsed.balance_after, Decimal("1000000.00"))
        self.assertEqual(parsed.amount_unit, "toman")

    def test_missing_unit_is_assumed_rial_and_flagged(self):
        """Bankino prints no unit at all. Rial is assumed — loudly."""
        parsed = parse_sms("بانک خاورمیانه\nخرید\n-1,100,000\nمانده 17,712,600")

        self.assertTrue(parsed.amount_was_assumed)
        self.assertEqual(parsed.amount_toman, Decimal("110000.00"))
        self.assertIn("واحد مبلغ در پیامک ذکر نشده بود؛ ریال در نظر گرفته شد. "
                      "اگر مبلغ به تومان است، اصلاح کنید.", parsed.warnings)
        # The assumption costs confidence but does not disqualify the row.
        self.assertLess(parsed.field_confidence["amount"], Decimal("1.000"))
        self.assertGreaterEqual(parsed.field_confidence["amount"], Decimal("0.300"))


# --------------------------------------------------------------------------
# Bank detection
# --------------------------------------------------------------------------


class BankDetectionTests(TestCase):
    def test_sender_id_wins(self):
        parsed = parse_sms("-1,100,000\nمانده 17,712,600", sender="20004861")

        self.assertEqual(parsed.bank_code, "bankino")
        self.assertEqual(parsed.bank_label, "بانکینو (خاورمیانه)")

    def test_sender_name_is_matched_case_insensitively(self):
        parsed = parse_sms("مبلغ 1,500,000 ریال واریز شد", sender="MELLIBANK")

        self.assertEqual(parsed.bank_code, "melli")

    def test_body_marker_when_the_sender_is_lost(self):
        """An exported or forwarded message keeps its body, not its sender."""
        parsed = parse_sms("بانک سامان\nخرید مبلغ 250,000 ریال")

        self.assertEqual(parsed.bank_code, "saman")

    def test_blu_is_not_mistaken_for_saman(self):
        parsed = parse_sms("بلو\nبرداشت پول\n2,500,000 ریال از حساب شما پرید.")

        self.assertEqual(parsed.bank_code, "blubank")

    def test_maskan_is_not_mistaken_for_melli(self):
        parsed = parse_sms("بانک مسکن\nخرید مبلغ 250,000 ریال")

        self.assertEqual(parsed.bank_code, "maskan")

    def test_unknown_bank_is_reported_and_does_not_stop_the_parse(self):
        parsed = parse_sms("از حساب شما مبلغ 500,000 ریال کسر گردید. موجودی: 1,500,000 ریال")

        self.assertEqual(parsed.bank_code, "unknown")
        self.assertEqual(parsed.bank_label, "بانک نامشخص")
        self.assertIn("بانک فرستنده شناسایی نشد؛ پیش از ثبت بررسی کنید.", parsed.warnings)
        # Everything else is still read: an unrecognised bank is not a failure.
        self.assertTrue(parsed.is_usable)


# --------------------------------------------------------------------------
# Noise
# --------------------------------------------------------------------------


class NoiseTests(TestCase):
    def test_one_time_password_is_not_a_transaction(self):
        parsed = parse_sms("رمز یکبار مصرف شما: 123456")

        self.assertFalse(parsed.is_transaction)
        self.assertEqual(parsed.noise_kind, "otp")
        self.assertFalse(parsed.is_usable)

    def test_one_time_password_that_mentions_an_amount_is_still_rejected(self):
        parsed = parse_sms("کد تایید: 54321\nمبلغ 500,000 ریال")

        self.assertFalse(parsed.is_transaction)
        self.assertEqual(parsed.noise_kind, "otp")

    def test_advertising_is_rejected(self):
        parsed = parse_sms("جشنواره قرعه کشی بانک سامان با تخفیف ویژه. مبلغ 500,000 ریال")

        self.assertFalse(parsed.is_transaction)
        self.assertEqual(parsed.noise_kind, "advertisement")

    def test_payment_request_is_rejected(self):
        parsed = parse_sms("درخواست پرداخت 500,000 ریال در انتظار تایید")

        self.assertFalse(parsed.is_transaction)
        self.assertEqual(parsed.noise_kind, "request")

    def test_empty_text(self):
        parsed = parse_sms("")

        self.assertFalse(parsed.is_transaction)
        self.assertEqual(parsed.noise_kind, "empty")


# --------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------


class DateTests(TestCase):
    def test_jalali_with_slashes(self):
        parsed = parse_sms("خرید مبلغ 250,000 ریال\n1405/06/15")

        self.assertEqual(parsed.occurred_on, dt.date(2026, 9, 6))
        self.assertEqual(parsed.date_source, "jalali")

    def test_jalali_with_dots_and_persian_digits(self):
        parsed = parse_sms("خرید مبلغ 250,000 ریال\n۱۴۰۵.۰۳.۲۲")

        self.assertEqual(parsed.occurred_on, dt.date(2026, 6, 12))

    def test_gregorian(self):
        parsed = parse_sms("خرید مبلغ 250,000 ریال\n2026-09-06")

        self.assertEqual(parsed.occurred_on, dt.date(2026, 9, 6))
        self.assertEqual(parsed.date_source, "gregorian")

    def test_no_date_is_null_and_costs_only_the_date_weight(self):
        parsed = parse_sms("از حساب شما مبلغ 500,000 ریال کسر گردید. موجودی: 1,500,000 ریال")

        self.assertIsNone(parsed.occurred_on)
        self.assertEqual(parsed.field_confidence["date"], Decimal("0.000"))
        self.assertIn("تاریخی در پیامک پیدا نشد؛ تاریخ را خودتان تعیین کنید.", parsed.warnings)
        self.assertTrue(parsed.is_usable)

    def test_clock_time_is_not_read_as_a_date(self):
        parsed = parse_sms("خرید مبلغ 250,000 ریال\n07:28")

        self.assertIsNone(parsed.occurred_on)


# --------------------------------------------------------------------------
# Numbers that are not money
# --------------------------------------------------------------------------


class AmountGuardTests(TestCase):
    def test_tracking_number_is_not_the_amount(self):
        parsed = parse_sms("شماره پیگیری: 45812 مبلغ 200,000 ریال خرید")

        self.assertEqual(parsed.amount_toman, Decimal("20000.00"))

    def test_card_suffix_is_not_money(self):
        parsed = parse_sms("خرید با کارت 7284 مبلغ 250,000 ریال. مانده: 1,500,000 ریال")

        self.assertEqual(parsed.amount_toman, Decimal("25000.00"))
        self.assertEqual(parsed.balance_after, Decimal("150000.00"))
        self.assertEqual(parsed.card_last4, "7284")

    def test_masked_card_supplies_the_last_four(self):
        parsed = parse_sms("خرید با کارت 6104 **** 7284 مبلغ 250,000 ریال")

        self.assertEqual(parsed.card_last4, "7284")

    def test_long_reference_number_is_not_money(self):
        parsed = parse_sms("خرید مبلغ 250,000 ریال شماره سند 123456789012")

        self.assertEqual(parsed.amount_toman, Decimal("25000.00"))
        self.assertIsNone(parsed.balance_after)

    def test_date_digits_are_not_amounts(self):
        parsed = parse_sms("خرید مبلغ 250,000 ریال 1405/06/15 موجودی 1,500,000 ریال")

        self.assertEqual(parsed.amount_toman, Decimal("25000.00"))
        self.assertEqual(parsed.balance_after, Decimal("150000.00"))
        self.assertEqual(parsed.occurred_on, dt.date(2026, 9, 6))

    def test_fee_below_the_floor_is_ignored(self):
        parsed = parse_sms("خرید مبلغ 1,000,000 ریال کارمزد 500 ریال. مانده: 3,000,000 ریال")

        self.assertEqual(parsed.amount_toman, Decimal("100000.00"))
        self.assertEqual(parsed.balance_after, Decimal("300000.00"))

    def test_merchant_is_captured_as_a_description_suggestion(self):
        parsed = parse_sms(
            "خرید\nپذیرنده: فروشگاه رفاه\nمبلغ 250,000 ریال. مانده: 1,500,000 ریال"
        )

        self.assertEqual(parsed.merchant, "فروشگاه رفاه")
        self.assertEqual(parsed.description, "فروشگاه رفاه")

    def test_description_falls_back_to_direction_and_bank(self):
        parsed = parse_sms("بانک مسکن خرید مبلغ 250,000 ریال")

        self.assertEqual(parsed.merchant, "")
        # The fallback is the generic direction label plus the bank label.
        self.assertEqual(parsed.description, "برداشت بانک مسکن")




