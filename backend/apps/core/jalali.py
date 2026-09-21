"""Jalali (Solar Hijri) calendar conversion and Persian date formatting.

Storage policy
--------------
Every date/datetime is stored in the database as a Gregorian ``date``/``datetime``
(``DateTimeField`` with ``USE_TZ=True``). Jalali is purely a *presentation and
input* concern, handled here. This keeps range queries, ordering, and future
database-side aggregation (PostgreSQL `date_trunc`, etc.) trivially correct.

The conversion algorithm below is the well-known arithmetic Jalali algorithm
(Birashk / Borkowski style) operating on the Julian Day Number. It is exact for
the supported year range and is deliberately dependency-free so the project has
no third-party calendar requirement.

Reference points used for validation:
    1400/01/01  ->  2021-03-21
    1405/01/01  ->  2026-03-21   (Nowruz 1405)
    1399/12/30  ->  2021-03-20   (1399 is a leap year)
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

PERSIAN_MONTHS = (
    "فروردین",
    "اردیبهشت",
    "خرداد",
    "تیر",
    "مرداد",
    "شهریور",
    "مهر",
    "آبان",
    "آذر",
    "دی",
    "بهمن",
    "اسفند",
)

# Gregorian month names — only used as a fallback / internal debugging aid.
GREGORIAN_MONTHS = (
    "ژانویه",
    "فوریه",
    "مارس",
    "آوریل",
    "مه",
    "ژوئن",
    "ژوئیه",
    "اوت",
    "سپتامبر",
    "اکتبر",
    "نوامبر",
    "دسامبر",
)

# Weekday names. Python's ``date.weekday()`` returns Monday == 0.
# The Persian week starts on Saturday.
PERSIAN_WEEKDAYS = (
    "دوشنبه",
    "سه‌شنبه",
    "چهارشنبه",
    "پنجشنبه",
    "جمعه",
    "شنبه",
    "یکشنبه",
)

# Short forms for compact UI (calendar grids, chips).
PERSIAN_WEEKDAYS_SHORT = (
    "د",
    "س",
    "چ",
    "پ",
    "ج",
    "ش",
    "ی",
)

# Saturday-first weekday ordering used by the date picker grid.
# Maps our canonical weekday index (Saturday == 0) to Python's weekday index.
SATURDAY_FIRST_TO_PYTHON = (5, 6, 0, 1, 2, 3, 4)

PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
LATIN_DIGITS = "0123456789"

_PERSIAN_TO_LATIN_MAP = str.maketrans(PERSIAN_DIGITS + "٠١٢٣٤٥٦٧٨٩", LATIN_DIGITS * 2)
_LATIN_TO_PERSIAN_MAP = str.maketrans(LATIN_DIGITS, PERSIAN_DIGITS)

# Persian thousands separator (U+066C ARABIC THOUSANDS SEPARATOR).
PERSIAN_THOUSANDS_SEPARATOR = "\u066c"

# JDN of 1/1/1 Jalali. Derived from the standard epoch: 1/1/1 Jalali fell on
# 622-03-22 in the proleptic Gregorian calendar, whose JDN is 1948321.
# Kept as a named constant because every conversion below is anchored to it.
JALALI_EPOCH_JDN = 1948321

# Gregorian date corresponding to 1/1/1 Jalali, in the proleptic Gregorian
# calendar. Both conversion directions are anchored to this single pair, which
# is what guarantees they are exact inverses of each other.
#
# Verified against 13 published reference dates plus an exhaustive
# day-by-day round trip over 1380-1420 (see apps/core/tests).
_GREGORIAN_JALALI_EPOCH = (622, 3, 21)


# --------------------------------------------------------------------------
# Conversion primitives
# --------------------------------------------------------------------------


def gregorian_to_jdn(year: int, month: int, day: int) -> int:
    """Convert a Gregorian (proleptic) date to a Julian Day Number.

    Standard Fliegel–Van Flandern algorithm. Valid for all Gregorian dates.
    """
    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12 * a - 3
    return (
        day
        + (153 * m + 2) // 5
        + 365 * y
        + y // 4
        - y // 100
        + y // 400
        - 32045
    )


def jdn_to_gregorian(jdn: int) -> tuple[int, int, int]:
    """Convert a Julian Day Number back to a Gregorian date."""
    a = jdn + 32044
    b = (4 * a + 3) // 146097
    c = a - (146097 * b) // 4
    d = (4 * c + 3) // 1461
    e = c - (1461 * d) // 4
    m = (5 * e + 2) // 153
    day = e - (153 * m + 2) // 5 + 1
    month = m + 3 - 12 * (m // 10)
    year = 100 * b + d - 4800 + m // 10
    return year, month, day


def _jalali_is_leap(jalali_year: int) -> bool:
    """True when ``jalali_year`` is a leap year (Esfand has 30 days).

    Uses the standard 33-year cycle rule that underlies the Jalali arithmetic
    calendar. Exact for years 1178..1633, which comfortably covers the range
    this application supports (see ``parse_jalali``).
    """
    return ((jalali_year + 12) % 33) % 4 == 1


def _jalali_month_days(jalali_year: int, jalali_month: int) -> int:
    """Number of days in a Jalali month."""
    if jalali_month <= 6:
        return 31
    if jalali_month <= 11:
        return 30
    return 30 if _jalali_is_leap(jalali_year) else 29


def gregorian_to_jalali(year: int, month: int, day: int) -> tuple[int, int, int]:
    """Convert a Gregorian date to (jalali_year, jalali_month, jalali_day)."""
    jdn = gregorian_to_jdn(year, month, day)
    return jdn_to_jalali(jdn)


def jdn_to_jalali(jdn: int) -> tuple[int, int, int]:
    """Convert a Julian Day Number to a Jalali date.

    Standard two-part algorithm: walk a 33-year cycle, then resolve the
    day-of-year into a month. Note the deliberate ``+ 1`` in the month/day
    arithmetic — it is required for the inverse of ``jalali_to_jdn`` to be
    exact, and was the source of an off-by-one before it was added.
    """
    epoch_jdn = gregorian_to_jdn(*_GREGORIAN_JALALI_EPOCH)

    # Days since the start of year 1, translated so the first 33-year block
    # starts at a known leap structure.
    days = jdn - epoch_jdn + 1

    cycle, remainder = divmod(days - 1, 12053)  # 12053 days per 33-year cycle
    jalali_year = 1 + 33 * cycle

    # Walk the remainder of the cycle year by year.
    while True:
        year_length = 366 if _jalali_is_leap(jalali_year) else 365
        if remainder < year_length:
            break
        remainder -= year_length
        jalali_year += 1

    # `remainder` is now the zero-based day-of-year.
    if remainder < 186:
        jalali_month = remainder // 31 + 1
        jalali_day = remainder % 31 + 1
    else:
        remainder -= 186
        jalali_month = remainder // 30 + 7
        jalali_day = remainder % 30 + 1

    return jalali_year, jalali_month, jalali_day


def jalali_to_gregorian(
    jalali_year: int, jalali_month: int, jalali_day: int
) -> tuple[int, int, int]:
    """Convert a Jalali date to (gregorian_year, gregorian_month, gregorian_day)."""
    jdn = jalali_to_jdn(jalali_year, jalali_month, jalali_day)
    return jdn_to_gregorian(jdn)


def jalali_to_jdn(jalali_year: int, jalali_month: int, jalali_day: int) -> int:
    """Convert a Jalali date to a Julian Day Number.

    Exact inverse of ``jdn_to_jalali``.
    """
    epoch_jdn = gregorian_to_jdn(*_GREGORIAN_JALALI_EPOCH)

    days = -1  # zero-based day-of-year accumulator

    # Whole 33-year cycles before this year.
    years_before = jalali_year - 1
    cycle = years_before // 33
    remainder_years = years_before % 33
    days += cycle * 12053
    for i in range(1, remainder_years + 1):
        days += 366 if _jalali_is_leap(i) else 365

    # Whole months before this month.
    for m in range(1, jalali_month):
        days += _jalali_month_days(jalali_year, m)

    days += jalali_day

    return epoch_jdn + days


# --------------------------------------------------------------------------
# Public helpers — the API the rest of the codebase should use
# --------------------------------------------------------------------------


def to_jalali(value: dt.date | dt.datetime) -> tuple[int, int, int]:
    """Return the Jalali (year, month, day) for any date/datetime."""
    if isinstance(value, dt.datetime):
        value = value.date()
    return gregorian_to_jalali(value.year, value.month, value.day)


def to_gregorian(jalali_year: int, jalali_month: int, jalali_day: int) -> dt.date:
    """Return a Gregorian ``date`` for a Jalali date."""
    y, m, d = jalali_to_gregorian(jalali_year, jalali_month, jalali_day)
    return dt.date(y, m, d)


def jalali_year_of(value: dt.date | dt.datetime) -> int:
    return to_jalali(value)[0]


def jalali_month_of(value: dt.date | dt.datetime) -> int:
    return to_jalali(value)[1]


def jalali_day_of(value: dt.date | dt.datetime) -> int:
    return to_jalali(value)[2]


def jalali_month_days(jalali_year: int, jalali_month: int) -> int:
    """Public wrapper for the month-length rule."""
    return _jalali_month_days(jalali_year, jalali_month)


def is_jalali_leap_year(jalali_year: int) -> bool:
    """Public wrapper for the leap-year rule."""
    return _jalali_is_leap(jalali_year)


def jalali_month_bounds(jalali_year: int, jalali_month: int) -> tuple[dt.date, dt.date]:
    """Inclusive first/last Gregorian date of a Jalali month.

    This is what range queries against the stored Gregorian dates should use.
    """
    first = to_gregorian(jalali_year, jalali_month, 1)
    last = to_gregorian(jalali_year, jalali_month, _jalali_month_days(jalali_year, jalali_month))
    return first, last


def days_in_jalali_month(jalali_year: int, jalali_month: int) -> int:
    return _jalali_month_days(jalali_year, jalali_month)


def jalali_weekday_index(value: dt.date | dt.datetime) -> int:
    """Weekday index where Saturday == 0 ... Friday == 6."""
    if isinstance(value, dt.datetime):
        value = value.date()
    # Python: Monday == 0. Shift so Saturday becomes 0.
    return (value.weekday() + 2) % 7


def jalali_weekday_name(value: dt.date | dt.datetime) -> str:
    """Full Persian weekday name, e.g. 'شنبه'."""
    return PERSIAN_WEEKDAYS[value.weekday()]


def jalali_weekday_name_short(value: dt.date | dt.datetime) -> str:
    """Single-letter Persian weekday abbreviation for calendar grids."""
    return PERSIAN_WEEKDAYS_SHORT[jalali_weekday_index(value)]


def add_jalali_months(jalali_year: int, jalali_month: int, delta: int) -> tuple[int, int]:
    """Shift a Jalali year/month pair by ``delta`` months.

    Out-of-range months are normalised, e.g. (1405, 12) + 1 -> (1406, 1).
    """
    zero_based = (jalali_year * 12) + (jalali_month - 1) + delta
    new_year, new_month = divmod(zero_based, 12)
    return new_year, new_month + 1


def current_jalali_month(today: dt.date | None = None) -> tuple[int, int]:
    """Return the Jalali (year, month) for today (or a supplied date)."""
    today = today or dt.date.today()
    jalali = to_jalali(today)
    return jalali[0], jalali[1]


# Valid Jalali years, used to reject nonsense before it reaches a query.
MIN_JALALI_YEAR = 1300
MAX_JALALI_YEAR = 1500


def resolve_month_param(
    request,
    *,
    default: tuple[int, int] | None = None,
) -> tuple[int, int]:
    """Resolve the requested Jalali month from a request's query parameters.

    This lives here, rather than being repeated in each view, because the bug it
    exists to prevent is subtle and was made four times: a view that reads only
    *some* of the accepted spellings silently falls back to the current month.
    The client then renders one month while the user believes they navigated to
    another, which looks like "the date filter does nothing" rather than like an
    error.

    Three spellings are accepted, because the endpoint is reached from more than
    one direction:

      * ``?month=1405-06`` (also ``1405/06``) — one packed value
      * ``?year=1405&month=6``           — the natural pair the web client sends
      * ``?year=1405&month_number=6``    — the original spelling, kept working

    The packed form is checked first so ``?month=1405-06`` cannot be parsed as a
    bare month number. A packed value is distinguished by containing ``-`` or
    ``/``; a bare integer ``month`` is only honoured when ``year`` accompanies
    it. Anything unparseable or out of range falls back to ``default`` (this
    month, unless the caller says otherwise) rather than raising — a malformed
    filter should show *something*, not a 500.
    """
    fallback = default or current_jalali_month()
    params = request.query_params

    def valid(year: int, month: int) -> bool:
        return MIN_JALALI_YEAR <= year <= MAX_JALALI_YEAR and 1 <= month <= 12

    raw = params.get("month")
    if raw is not None:
        text = str(raw).strip().replace("/", "-")
        if "-" in text:
            parts = text.split("-")
            if len(parts) == 2:
                try:
                    year, month = int(parts[0]), int(parts[1])
                    if valid(year, month):
                        return year, month
                except ValueError:
                    pass
        else:
            # `?year=&month=` — the pair the web client actually sends.
            year_raw = params.get("year")
            if year_raw is not None:
                try:
                    year, month = int(year_raw), int(text)
                    if valid(year, month):
                        return year, month
                except ValueError:
                    pass

    year_raw = params.get("year")
    month_raw = params.get("month_number")
    if year_raw and month_raw:
        try:
            year, month = int(year_raw), int(month_raw)
            if valid(year, month):
                return year, month
        except ValueError:
            pass

    return fallback



def month_progress(jalali_year: int, jalali_month: int, today: dt.date | None = None) -> dict:
    """How far through a Jalali month we are.

    This drives the "spending pace vs. time pace" comparison that the budget
    analysis is built on. Returns ``days_elapsed``, ``days_in_month`` and
    ``percent_elapsed`` (a float 0..100).

    For a month entirely in the past, elapsed == total (100%). For a future
    month, elapsed counts as 0 so nothing is flagged as behind schedule.
    """
    today = today or dt.date.today()
    total_days = _jalali_month_days(jalali_year, jalali_month)
    first_day, last_day = jalali_month_bounds(jalali_year, jalali_month)

    if today < first_day:
        days_elapsed = 0
    elif today > last_day:
        days_elapsed = total_days
    else:
        days_elapsed = (today - first_day).days + 1

    percent = (days_elapsed / total_days * 100.0) if total_days else 0.0
    return {
        "days_elapsed": days_elapsed,
        "days_in_month": total_days,
        "percent_elapsed": round(percent, 1),
        "is_current_month": first_day <= today <= last_day,
    }


# --------------------------------------------------------------------------
# Persian formatting
# --------------------------------------------------------------------------


def to_persian_digits(value: str | int) -> str:
    """Convert Latin digits in ``value`` to Persian digits."""
    return str(value).translate(_LATIN_TO_PERSIAN_MAP)


def to_latin_digits(value: str) -> str:
    """Normalise Persian/Arabic-Indic digits back to Latin.

    Applied on every incoming date/number string so a user typing ۱۴۰۵/۰۷/۰۱
    is understood identically to 1405/07/01.
    """
    return str(value).translate(_PERSIAN_TO_LATIN_MAP)


def format_number(value: int | float | Decimal, *, persian: bool = True) -> str:
    """Format a number with thousands separators, optionally in Persian digits.

    Uses the Arabic thousands separator ``٬`` (U+066C) rather than a comma.
    This is the correct character for Persian numeric typography and it is what
    the product spec asks for (``۱۲۳٬۴۵۶``). A plain comma renders with the
    Latin-glyph left-to-right shaping and looks out of place beside Persian
    digits.
    """
    if isinstance(value, Decimal):
        # Drop a trailing .00 while preserving genuine decimals.
        normalised = value.normalize()
        if normalised == normalised.to_integral_value():
            value = int(normalised)
        else:
            value = float(normalised)

    if isinstance(value, float):
        rounded = round(value, 2)
        text = f"{rounded:,.2f}".rstrip("0").rstrip(".")
    else:
        text = f"{int(value):,}"

    if persian:
        # Swap the ASCII grouping comma for the Persian thousands separator.
        # Only in the Persian variant: the Latin variant is meant to be
        # copy-pasteable into other tools, where U+066C is not a digit
        # separator at all.
        return to_persian_digits(text.replace(",", PERSIAN_THOUSANDS_SEPARATOR))

    return text


def format_money(
    amount: Decimal | int | float,
    *,
    unit: str = "تومان",
    persian: bool = True,
    with_unit: bool = True,
) -> str:
    """Format a monetary amount the way Persian finance UIs expect.

    Example: ``Decimal('250000')`` -> ``'۲۵۰٬۰۰۰ تومان'``
    """
    text = format_number(amount, persian=persian)
    if not with_unit:
        return text
    return f"{text} {unit}"


def format_percent(value: float | Decimal, *, persian: bool = True, decimals: int = 0) -> str:
    """Format a percentage, e.g. 65.4 -> '۶۵٪'."""
    rounded = round(float(value), decimals)
    if decimals == 0:
        text = str(int(rounded))
    else:
        text = f"{rounded:.{decimals}f}".rstrip("0").rstrip(".")
    sign = "٪"
    return (to_persian_digits(text) if persian else text) + sign


def month_label(jalali_year: int, jalali_month: int, *, persian: bool = True) -> str:
    """``مهر ۱۴۰۵`` — the human label for a Jalali month.

    This is the single source of truth for that string. It was previously
    assembled inline in five places, and one of them
    (`budgets.services.empty_analysis`) omitted the digit conversion — so a month
    *with* a budget was labelled ``شهریور ۱۴۰۵`` while a month *without* one was
    labelled ``فروردین 1405``. Two numeral systems for the same concept, in the
    same response shape.

    An out-of-range month yields just the year rather than raising: callers
    build labels for whatever month they were asked about, and a slightly odd
    label beats a 500.
    """
    if not 1 <= jalali_month <= 12:
        return str(jalali_year)
    return (
        to_persian_digits(f"{PERSIAN_MONTHS[jalali_month - 1]} {jalali_year}")
        if persian
        else f"{PERSIAN_MONTHS[jalali_month - 1]} {jalali_year}"
    )


def format_jalali(
    value: dt.date | dt.datetime,
    *,
    style: str = "numeric",
    persian: bool = True,
) -> str:
    """Format a date as a Persian/Jalali string.

    Styles:
        ``numeric``  -> ۱۴۰۵/۰۷/۰۱
        ``short``    -> ۱ مهر ۱۴۰۵
        ``long``     -> ۱ مهر ۱۴۰۵
        ``full``     -> شنبه ۱ مهر ۱۴۰۵
        ``month``    -> مهر ۱۴۰۵
        ``month_year`` -> مهر ۱۴۰۵
    """
    if isinstance(value, dt.datetime):
        value = value.date()

    jy, jm, jd = to_jalali(value)

    if style == "numeric":
        raw = f"{jy:04d}/{jm:02d}/{jd:02d}"
        return to_persian_digits(raw) if persian else raw

    if style == "month":
        raw = f"{PERSIAN_MONTHS[jm - 1]} {jy:04d}"
        return to_persian_digits(raw) if persian else raw

    if style == "month_year":
        raw = f"{PERSIAN_MONTHS[jm - 1]} {jy:04d}"
        return to_persian_digits(raw) if persian else raw

    day_month = f"{jd} {PERSIAN_MONTHS[jm - 1]} {jy:04d}"
    day_month = to_persian_digits(day_month) if persian else day_month

    if style == "full":
        return f"{jalali_weekday_name(value)} {day_month}"

    # `short` and `long` intentionally render the same in Persian: the word
    # "میلیادی" style suffixes do not exist here, so a distinct long form would
    # be inventing a convention. Documented rather than silently diverging.
    return day_month


def format_jalali_datetime(value: dt.datetime, *, persian: bool = True) -> str:
    """Format a datetime as 'شنبه ۱ مهر ۱۴۰۵ — ۱۴:۳۰'."""
    date_part = format_jalali(value, style="full", persian=persian)
    time_part = f"{value.hour:02d}:{value.minute:02d}"
    if persian:
        time_part = to_persian_digits(time_part)
    return f"{date_part} — {time_part}"


def parse_jalali(value: str) -> dt.date:
    """Parse a Persian date string into a Gregorian ``date``.

    Accepts ``۱۴۰۵/۰۷/۰۱``, ``1405/7/1``, ``1405-07-01`` and any mix of
    Persian/Latin digits. Raises ``ValueError`` on malformed input so callers
    can surface a localized validation error.
    """
    if not value:
        raise ValueError("تاریخ وارد نشده است.")

    cleaned = to_latin_digits(str(value)).strip()
    for separator in ("-", ".", "\u200c"):
        cleaned = cleaned.replace(separator, "/")
    # Collapse repeated separators from doubled slashes.
    parts = [p for p in cleaned.split("/") if p != ""]

    if len(parts) != 3:
        raise ValueError("قالب تاریخ نامعتبر است. نمونه درست: ۱۴۰۵/۰۷/۰۱")

    try:
        jy, jm, jd = (int(p) for p in parts)
    except ValueError as exc:
        raise ValueError("قالب تاریخ نامعتبر است. نمونه درست: ۱۴۰۵/۰۷/۰۱") from exc

    if not 1200 <= jy <= 1600:
        raise ValueError("سال باید بین ۱۲۰۰ و ۱۶۰۰ باشد.")
    if not 1 <= jm <= 12:
        raise ValueError("ماه باید بین ۱ و ۱۲ باشد.")
    max_day = _jalali_month_days(jy, jm)
    if not 1 <= jd <= max_day:
        raise ValueError(f"روز باید بین ۱ و {max_day} باشد.")

    return to_gregorian(jy, jm, jd)


@dataclass(frozen=True)
class JalaliDate:
    """Lightweight immutable Jalali date value object."""

    year: int
    month: int
    day: int

    @classmethod
    def from_date(cls, value: dt.date | dt.datetime) -> "JalaliDate":
        return cls(*to_jalali(value))

    @property
    def month_name(self) -> str:
        return PERSIAN_MONTHS[self.month - 1]

    @property
    def days_in_month(self) -> int:
        return _jalali_month_days(self.year, self.month)

    def to_gregorian(self) -> dt.date:
        return to_gregorian(self.year, self.month, self.day)

    def format(self, style: str = "numeric", persian: bool = True) -> str:
        return format_jalali(self.to_gregorian(), style=style, persian=persian)
