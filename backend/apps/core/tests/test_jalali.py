"""Tests for the Jalali calendar engine and Persian formatting helpers.

The calendar is the one component where a silent bug would corrupt every date
in the product, so it is tested from three angles:

1.  Published reference dates (spot checks against known conversions).
2.  An exhaustive day-by-day round trip, which catches drift that spot checks
    on Nowruz alone would miss.
3.  Structural invariants (month lengths, leap-year cycle, year totals).
"""

from __future__ import annotations

import datetime as dt
from unittest.mock import patch
from decimal import Decimal

from django.test import SimpleTestCase

from apps.core.jalali import (
    PERSIAN_MONTHS,
    PERSIAN_THOUSANDS_SEPARATOR,
    days_in_jalali_month,
    format_jalali,
    format_money,
    format_number,
    month_label,
    resolve_month_param,
    format_percent,
    gregorian_to_jalali,
    is_jalali_leap_year,
    jalali_month_bounds,
    jalali_to_gregorian,
    month_progress,
    parse_jalali,
    to_latin_digits,
    to_persian_digits,
)

# (gregorian_date, expected_jalali) tuples from published calendar tables.
REFERENCE_DATES = [
    ((2021, 3, 21), (1400, 1, 1)),
    ((2026, 3, 21), (1405, 1, 1)),
    ((2021, 3, 20), (1399, 12, 30)),  # 1399 is a leap year
    ((2022, 3, 21), (1401, 1, 1)),
    ((2023, 3, 21), (1402, 1, 1)),
    ((2024, 3, 20), (1403, 1, 1)),
    ((2025, 3, 21), (1404, 1, 1)),
    ((2026, 9, 11), (1405, 6, 20)),
    ((2026, 9, 21), (1405, 6, 30)),
    ((2026, 9, 22), (1405, 6, 31)),  # 1405 is common but has 31-day Shahrivar... see note
    ((1979, 2, 11), (1357, 11, 22)),
    ((2000, 1, 1), (1378, 10, 11)),
    ((1990, 1, 1), (1368, 10, 11)),
    ((2021, 7, 1), (1400, 4, 10)),
    ((2011, 5, 1), (1390, 2, 11)),
]


class GregorianToJalaliTests(SimpleTestCase):
    def test_reference_dates(self):
        for gregorian, expected in REFERENCE_DATES:
            with self.subTest(gregorian=gregorian):
                self.assertEqual(gregorian_to_jalali(*gregorian), expected)

    def test_reference_dates_inverse(self):
        for gregorian, jalali in REFERENCE_DATES:
            with self.subTest(jalali=jalali):
                self.assertEqual(jalali_to_gregorian(*jalali), gregorian)

    def test_exhaustive_round_trip_over_40_years(self):
        """Every single day from 1380 to 1420 must survive a round trip.

        This is the test that actually protects us: an off-by-one that only
        appears after a leap year is invisible to Nowruz-only spot checks.
        """
        current = dt.date(1380, 1, 1)
        end = dt.date(1420, 12, 31)
        checked = 0

        while current <= end:
            jalali = gregorian_to_jalali(current.year, current.month, current.day)
            restored = jalali_to_gregorian(*jalali)
            self.assertEqual(
                restored,
                (current.year, current.month, current.day),
                msg=f"round trip failed for {current} via {jalali}",
            )
            current += dt.timedelta(days=1)
            checked += 1

        self.assertEqual(checked, 14975)

    def test_accepts_datetime(self):
        moment = dt.datetime(2026, 9, 20, 14, 30)
        self.assertEqual(gregorian_to_jalali(2026, 9, 20), gregorian_to_jalali(2026, 9, 20))
        self.assertEqual(gregorian_to_jalali(moment.year, moment.month, moment.day), (1405, 6, 29))


class LeapYearTests(SimpleTestCase):
    def test_known_leap_years(self):
        # 1399 and 1403 are leap; 1400, 1404 and 1405 are not.
        self.assertTrue(is_jalali_leap_year(1399))
        self.assertTrue(is_jalali_leap_year(1403))
        self.assertFalse(is_jalali_leap_year(1400))
        self.assertFalse(is_jalali_leap_year(1404))
        self.assertFalse(is_jalali_leap_year(1405))

    def test_year_length_matches_leap_status(self):
        for year in range(1390, 1420):
            total = sum(days_in_jalali_month(year, m) for m in range(1, 13))
            expected = 366 if is_jalali_leap_year(year) else 365
            with self.subTest(year=year):
                self.assertEqual(total, expected)

    def test_first_six_months_always_31_days(self):
        for year in range(1390, 1420):
            for month in range(1, 7):
                with self.subTest(year=year, month=month):
                    self.assertEqual(days_in_jalali_month(year, month), 31)

    def test_esfand_29_or_30(self):
        self.assertEqual(days_in_jalali_month(1399, 12), 30)
        self.assertEqual(days_in_jalali_month(1400, 12), 29)
        self.assertEqual(days_in_jalali_month(1405, 12), 29)


class MonthBoundsTests(SimpleTestCase):
    def test_shahrivar_1405_bounds(self):
        first, last = jalali_month_bounds(1405, 6)
        # 1405/06/01 and 1405/06/31
        self.assertEqual(first, dt.date(2026, 8, 23))
        self.assertEqual(last, dt.date(2026, 9, 22))

    def test_bounds_span_declared_month_length(self):
        for year, month in [(1405, 1), (1405, 6), (1405, 12), (1403, 12), (1400, 12)]:
            first, last = jalali_month_bounds(year, month)
            span = (last - first).days + 1
            with self.subTest(year=year, month=month):
                self.assertEqual(span, days_in_jalali_month(year, month))


class MonthProgressTests(SimpleTestCase):
    def test_mid_month_progress(self):
        # 1405/06/29 against a 31-day month.
        progress = month_progress(1405, 6, dt.date(2026, 9, 20))
        self.assertEqual(progress["days_elapsed"], 29)
        self.assertEqual(progress["days_in_month"], 31)
        self.assertAlmostEqual(progress["percent_elapsed"], 93.5, places=1)
        self.assertTrue(progress["is_current_month"])

    def test_past_month_is_complete(self):
        progress = month_progress(1405, 5, dt.date(2026, 9, 20))
        self.assertEqual(progress["days_elapsed"], progress["days_in_month"])
        self.assertAlmostEqual(progress["percent_elapsed"], 100.0, places=1)

    def test_future_month_has_no_elapsed_time(self):
        progress = month_progress(1405, 8, dt.date(2026, 9, 20))
        self.assertEqual(progress["days_elapsed"], 0)
        self.assertAlmostEqual(progress["percent_elapsed"], 0.0, places=1)

    def test_progress_never_exceeds_100(self):
        for month in range(1, 13):
            progress = month_progress(1405, month, dt.date(2026, 9, 20))
            with self.subTest(month=month):
                self.assertLessEqual(progress["percent_elapsed"], 100.0)
                self.assertGreaterEqual(progress["percent_elapsed"], 0.0)


class ParseJalaliTests(SimpleTestCase):
    def test_parses_persian_digits(self):
        self.assertEqual(parse_jalali("۱۴۰۵/۰۶/۲۹"), dt.date(2026, 9, 20))

    def test_parses_latin_digits(self):
        self.assertEqual(parse_jalali("1405/06/29"), dt.date(2026, 9, 20))

    def test_parses_without_padding(self):
        self.assertEqual(parse_jalali("1405/6/29"), dt.date(2026, 9, 20))

    def test_parses_dash_separator(self):
        self.assertEqual(parse_jalali("1405-06-29"), dt.date(2026, 9, 20))

    def test_round_trips_with_format(self):
        original = dt.date(2026, 9, 20)
        self.assertEqual(parse_jalali(format_jalali(original, style="numeric")), original)

    def test_rejects_malformed_input(self):
        for bad in ["", "not-a-date", "1405/06", "1405/06/29/01"]:
            with self.subTest(value=bad), self.assertRaises(ValueError):
                parse_jalali(bad)

    def test_rejects_out_of_range_parts(self):
        for bad in ["1405/13/01", "1405/00/01", "1405/06/32", "1100/01/01"]:
            with self.subTest(value=bad), self.assertRaises(ValueError):
                parse_jalali(bad)

    def test_rejects_esfand_30_in_common_year(self):
        # 1405 is a common year, so 1405/12/30 does not exist.
        with self.assertRaises(ValueError):
            parse_jalali("1405/12/30")

    def test_accepts_esfand_30_in_leap_year(self):
        self.assertEqual(parse_jalali("1399/12/30"), dt.date(2021, 3, 20))


class FormattingTests(SimpleTestCase):
    def test_persian_digit_conversion(self):
        self.assertEqual(to_persian_digits("1405"), "۱۴۰۵")
        self.assertEqual(to_latin_digits("۱۴۰۵"), "1405")

    def test_format_money(self):
        # Persian grouping uses U+066C ARABIC THOUSANDS SEPARATOR, not a comma.
        self.assertEqual(format_money(250000), "۲۵۰٬۰۰۰ تومان")
        self.assertEqual(format_money(16000000), "۱۶٬۰۰۰٬۰۰۰ تومان")
        self.assertEqual(format_money(Decimal("150000000")), "۱۵۰٬۰۰۰٬۰۰۰ تومان")
        self.assertEqual(format_money(0), "۰ تومان")

    def test_format_money_uses_persian_separator_not_ascii_comma(self):
        """A plain comma is the wrong glyph for Persian numeric typography."""
        formatted = format_money(250000)
        self.assertIn(PERSIAN_THOUSANDS_SEPARATOR, formatted)
        self.assertNotIn(",", formatted)

    def test_format_money_negative(self):
        # Negative amounts must keep the minus sign and stay readable.
        self.assertIn("۲۵۰٬۰۰۰", format_money(-250000))

    def test_format_money_without_unit(self):
        self.assertEqual(format_money(250000, with_unit=False), "۲۵۰٬۰۰۰")

    def test_format_money_latin(self):
        # The Latin variant keeps ASCII digits and the ASCII comma, because it
        # is meant to be copy-pasteable into other tools.
        self.assertEqual(format_money(250000, persian=False), "250,000 تومان")

    def test_format_number_rounds_decimals(self):
        self.assertEqual(format_number(Decimal("1000000.00")), "۱٬۰۰۰٬۰۰۰")
        self.assertEqual(format_number(Decimal("1500.5")), "۱٬۵۰۰.۵")

    def test_format_percent(self):
        self.assertEqual(format_percent(65), "۶۵٪")
        self.assertEqual(format_percent(0), "۰٪")
        self.assertEqual(format_percent(100), "۱۰۰٪")

    def test_format_jalali_styles(self):
        value = dt.date(2026, 9, 20)  # 1405/06/29, a Sunday
        self.assertEqual(format_jalali(value, style="numeric"), "۱۴۰۵/۰۶/۲۹")
        self.assertEqual(format_jalali(value, style="short"), "۲۹ شهریور ۱۴۰۵")
        self.assertEqual(format_jalali(value, style="month"), "شهریور ۱۴۰۵")
        self.assertTrue(format_jalali(value, style="full").startswith("یکشنبه"))
        self.assertIn("شهریور", format_jalali(value, style="full"))

    def test_format_jalali_never_leaks_gregorian_year(self):
        """A user-facing date must never contain the Gregorian year."""
        for day in range(1, 29):
            value = dt.date(2026, 9, day)
            rendered = format_jalali(value, style="numeric")
            with self.subTest(day=day):
                self.assertTrue(rendered.startswith("۱۴۰۵"), rendered)

    def test_all_persian_month_names_present(self):
        self.assertEqual(len(PERSIAN_MONTHS), 12)
        self.assertEqual(PERSIAN_MONTHS[0], "فروردین")
        self.assertEqual(PERSIAN_MONTHS[11], "اسفند")


class _FakeRequest:
    """Minimal stand-in for a DRF request — the resolver only reads params."""

    def __init__(self, **params):
        self.query_params = {k: str(v) for k, v in params.items() if v is not None}


class ResolveMonthParamTests(SimpleTestCase):
    """The month resolver, which is shared by budgets, insights, reports and the
    transaction calendar.

    A view that understood only *some* of the accepted spellings silently fell
    back to the current month, so changing the filter appeared to do nothing at
    all. These tests pin every spelling the client might use, because that
    silent fallback is exactly the failure mode being guarded against.
    """

    def test_reads_the_year_and_month_pair(self):
        """The web client sends ?year=1405&month=5 — this is the regression."""
        self.assertEqual(resolve_month_param(_FakeRequest(year=1405, month=5)), (1405, 5))

    def test_reads_a_packed_month(self):
        self.assertEqual(resolve_month_param(_FakeRequest(month="1405-06")), (1405, 6))

    def test_reads_a_packed_month_with_slashes(self):
        self.assertEqual(resolve_month_param(_FakeRequest(month="1405/06")), (1405, 6))

    def test_reads_the_legacy_month_number_spelling(self):
        self.assertEqual(
            resolve_month_param(_FakeRequest(year=1405, month_number=6)), (1405, 6)
        )

    def test_a_packed_value_is_never_mistaken_for_a_bare_number(self):
        # `1405-06` could be read as a bare month if the packed check were not
        # tried first; it must resolve to June, not to month 1405.
        self.assertEqual(resolve_month_param(_FakeRequest(month="1405-06")), (1405, 6))

    def test_matches_the_current_month_when_nothing_is_supplied(self):
        with patch("apps.core.jalali.current_jalali_month", return_value=(1405, 6)):
            self.assertEqual(resolve_month_param(_FakeRequest()), (1405, 6))

    def test_falls_back_rather_than_raising_on_junk(self):
        for junk in [
            {"month": "abc"},
            {"month": "1405-"},
            {"month": "-06"},
            {"year": "x", "month": "6"},
            {"year": "1405", "month": "99"},
            {"year": "1200", "month": "6"},
            {"year": "1405", "month_number": "0"},
        ]:
            with self.subTest(**junk):
                self.assertEqual(
                    resolve_month_param(_FakeRequest(**junk)), (1405, 6),
                    f"{junk} should fall back to the default month",
                )

    def test_honours_an_explicit_default(self):
        self.assertEqual(
            resolve_month_param(_FakeRequest(), default=(1404, 1)), (1404, 1)
        )

    def test_a_bare_month_without_a_year_is_ignored(self):
        # `?month=5` alone is ambiguous, so it is not a month number; fall back.
        with patch("apps.core.jalali.current_jalali_month", return_value=(1405, 6)):
            self.assertEqual(resolve_month_param(_FakeRequest(month="5")), (1405, 6))


class MonthLabelTests(SimpleTestCase):
    """`month_label` is the one place a month label is built.

    It was previously assembled inline in five places and one of them forgot the
    digit conversion, so the same response shape labelled a month with a budget
    `شهریور ۱۴۰۵` and a month without one `فروردین 1405`. These tests pin the
    single consistent behaviour.
    """

    def test_uses_persian_digits(self):
        self.assertEqual(month_label(1405, 6), "شهریور ۱۴۰۵")
        self.assertEqual(month_label(1405, 1), "فروردین ۱۴۰۵")

    def test_never_mixes_digit_styles(self):
        """The whole point: no month may come out with Latin digits."""
        for month in range(1, 13):
            with self.subTest(month=month):
                label = month_label(1405, month)
                self.assertTrue(
                    any("۰" <= c <= "۹" for c in label),
                    f"{label} has no Persian digit",
                )
                self.assertFalse(
                    any("0" <= c <= "9" for c in label),
                    f"{label} leaked a Latin digit",
                )

    def test_every_month_has_a_distinct_label(self):
        labels = {month_label(1405, m) for m in range(1, 13)}
        self.assertEqual(len(labels), 12)

    def test_can_render_latin_when_asked(self):
        self.assertEqual(month_label(1405, 6, persian=False), "شهریور 1405")

    def test_out_of_range_month_degrades_to_the_year(self):
        # A slightly odd label beats a 500 for a month the caller asked about.
        self.assertEqual(month_label(1405, 13), "1405")
        self.assertEqual(month_label(1405, 0), "1405")
