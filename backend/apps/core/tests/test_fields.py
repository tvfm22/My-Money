"""Tests for the Jalali-aware input fields.

The API must accept Persian/Jalali dates because that is the only calendar the
UI shows. These tests pin down the disambiguation rule, the validation of
out-of-range Jalali dates, and that the stored value is always Gregorian.
"""

from __future__ import annotations

import datetime as dt

from django.test import SimpleTestCase
from rest_framework import serializers

from apps.core.fields import JalaliDateField


class _Wrapper(serializers.Serializer):
    """Minimal serializer so field errors surface the way they do in a view."""

    date = JalaliDateField()


class JalaliDateFieldTests(SimpleTestCase):
    def test_accepts_jalali_with_dashes(self):
        serializer = _Wrapper(data={"date": "1405-06-29"})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["date"], dt.date(2026, 9, 20))

    def test_accepts_jalali_with_slashes(self):
        serializer = _Wrapper(data={"date": "1405/06/29"})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["date"], dt.date(2026, 9, 20))

    def test_accepts_jalali_with_persian_digits(self):
        serializer = _Wrapper(data={"date": "۱۴۰۵/۰۶/۲۹"})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["date"], dt.date(2026, 9, 20))

    def test_accepts_gregorian_iso(self):
        serializer = _Wrapper(data={"date": "2026-09-20"})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["date"], dt.date(2026, 9, 20))

    def test_both_calendars_agree_on_today(self):
        jalali = _Wrapper(data={"date": "1405/06/29"})
        gregorian = _Wrapper(data={"date": "2026-09-20"})
        jalali.is_valid()
        gregorian.is_valid()
        self.assertEqual(jalali.validated_data["date"], gregorian.validated_data["date"])

    def test_rejects_out_of_range_month(self):
        serializer = _Wrapper(data={"date": "1405/13/01"})
        self.assertFalse(serializer.is_valid())
        self.assertIn("date", serializer.errors)

    def test_rejects_out_of_range_day(self):
        # Mehr (7th month) has 30 days, never 31.
        serializer = _Wrapper(data={"date": "1405/07/31"})
        self.assertFalse(serializer.is_valid())
        self.assertIn("date", serializer.errors)

    def test_accepts_the_last_day_of_a_31_day_month(self):
        # Shahrivar has 31 days even in a common year.
        serializer = _Wrapper(data={"date": "1405/06/31"})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["date"], dt.date(2026, 9, 22))

    def test_accepts_the_last_day_of_esfand_in_a_leap_year(self):
        serializer = _Wrapper(data={"date": "1399/12/30"})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["date"], dt.date(2021, 3, 20))

    def test_rejects_esfand_30_in_a_common_year(self):
        # 1405 is a common year, so Esfand has 29 days.
        serializer = _Wrapper(data={"date": "1405/12/30"})
        self.assertFalse(serializer.is_valid())
        self.assertIn("date", serializer.errors)

    def test_rejects_garbage(self):
        for value in ["not-a-date", "1405", "", "1405/ab/01"]:
            with self.subTest(value=value):
                serializer = _Wrapper(data={"date": value})
                self.assertFalse(serializer.is_valid())

    def test_accepts_a_python_date(self):
        serializer = _Wrapper(data={"date": dt.date(2026, 9, 20)})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["date"], dt.date(2026, 9, 20))

    def test_representation_is_iso_gregorian(self):
        field = JalaliDateField()
        self.assertEqual(field.to_representation(dt.date(2026, 9, 20)), "2026-09-20")

    def test_error_message_is_persian(self):
        serializer = _Wrapper(data={"date": "1405/13/45"})
        serializer.is_valid()
        message = str(serializer.errors["date"][0])
        self.assertTrue(
            any("\u0600" <= ch <= "\u06ff" for ch in message),
            f"date error was not in Persian: {message}",
        )

    def test_round_trip_across_a_year_boundary(self):
        """1404/12/29 and 1405/01/01 must not collapse onto the same day."""
        last_of_1404 = _Wrapper(data={"date": "1404/12/29"})
        first_of_1405 = _Wrapper(data={"date": "1405/01/01"})
        last_of_1404.is_valid()
        first_of_1405.is_valid()
        self.assertEqual(
            (first_of_1405.validated_data["date"] - last_of_1404.validated_data["date"]).days,
            1,
        )
