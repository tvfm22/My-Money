"""Reusable DRF fields for Persian/Jalali input.

The product presents every date in Jalali, so the API must accept Jalali input
too — otherwise the client would have to convert, and the conversion logic
would exist in two places (and drift). These fields keep one implementation,
on the server, and accept both formats so the API stays usable from tools that
speak ISO.
"""

from __future__ import annotations

import datetime as dt

from rest_framework import serializers

from apps.core.jalali import (
    days_in_jalali_month,
    is_jalali_leap_year,
    to_gregorian,
    to_latin_digits,
)

JALALI_FORMAT_HINT = "YYYY-MM-DD"


class JalaliDateField(serializers.DateField):
    """A date field that accepts Persian/Jalali input as well as ISO.

    Accepted inputs (all equivalent)::

        1405-06-29          Jalali
        1405/06/29          Jalali, slashed
        ۱۴۰۵/۰۶/۲۹          Jalali, Persian digits
        2026-09-20          Gregorian ISO

    The rule for disambiguation is the year: a four-digit year of 1700 or less
    is a Jalali year (the Jalali era is currently in the 1400s, and 1700 is a
    comfortable ceiling above it while staying far below any plausible
    Gregorian year). Anything larger is treated as Gregorian.

    Output is always a ``datetime.date``, so the model layer sees plain
    Gregorian dates and stays independent of the calendar used for display.
    """

    # Above this year value, the input must be Gregorian. 1700 is chosen to sit
    # well above the Jalali era (14xx) and well below any Gregorian date a
    # personal finance app would plausibly receive.
    JALALI_YEAR_CEILING = 1700

    default_error_messages = {
        "invalid": "فرمت تاریخ اشتباه است. از یکی از این قالب‌ها استفاده کنید: "
        "۱۴۰۵/۰۶/۲۹ یا 2026-09-20.",
        "invalid_jalali": "تاریخ شمسی وارد شده معتبر نیست.",
    }

    def to_internal_value(self, value):
        if value in (None, "", "null"):
            if self.allow_null:
                return None
            self.fail("required")

        if isinstance(value, dt.datetime):
            return value.date()
        if isinstance(value, dt.date):
            return value

        text = to_latin_digits(str(value)).strip()
        # Normalise every plausible separator to a single form.
        for separator in ("/", ".", "T", " "):
            text = text.replace(separator, "-")

        parts = text.split("-")
        # Trim a time component if one came along for the ride.
        parts = [p for p in parts if p]
        if len(parts) < 3:
            self.fail("invalid")

        try:
            year, month, day = (int(parts[0]), int(parts[1]), int(parts[2]))
        except (TypeError, ValueError):
            self.fail("invalid")

        if year < self.JALALI_YEAR_CEILING:
            # Jalali input: validate the month/day against the Jalali calendar
            # before converting. `to_gregorian` is a pure arithmetic
            # conversion and will happily roll 1405/13/01 over into the next
            # year, which is not what a user typing an invalid date means.
            if not 1 <= month <= 12:
                self.fail("invalid_jalali")
            if not 1 <= day <= days_in_jalali_month(year, month):
                self.fail("invalid_jalali")
            try:
                return to_gregorian(year, month, day)
            except (ValueError, TypeError):
                self.fail("invalid_jalali")

        # Gregorian input.
        try:
            return dt.date(year, month, day)
        except ValueError:
            self.fail("invalid")

    def to_representation(self, value):
        """Emit ISO, because the client formats dates for display itself.

        The API also returns a pre-formatted Jalali string in a sibling
        ``*_display`` field, which is what the UI actually renders.
        """
        if value is None:
            return None
        return value.isoformat()
