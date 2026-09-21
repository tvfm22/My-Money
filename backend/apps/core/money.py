"""Money handling primitives.

Project rule: money is ALWAYS ``decimal.Decimal``. Never ``float``. A float can
represent 0.1 only approximately, and those errors accumulate across thousands
of transactions into balances that do not reconcile. The helpers here exist so
that the correct habit is also the convenient one.

Amounts are stored as ``DecimalField(max_digits=18, decimal_places=2)``:
18 total digits with 2 decimal places leaves 16 integer digits, which is
roughly 10^16 Rial — far beyond any personal finance figure, while still
leaving headroom for multi-currency conversion later.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# Two decimal places is the storage precision. Toman has no practical subunit
# today, but keeping 2 places means switching to a currency with cents (or
# recording exchange rates) does not require a migration.
MONEY_PRECISION = Decimal("0.01")

# Percentage arithmetic precision — 2 decimal places is more than enough for
# budget progress display and avoids float artefacts in comparisons.
PERCENT_PRECISION = Decimal("0.01")

ZERO = Decimal("0.00")


def to_decimal(value: Decimal | int | str | float | None) -> Decimal:
    """Coerce any numeric input to an exact ``Decimal``.

    Floats are routed through ``str`` so that ``to_decimal(0.1)`` yields exactly
    ``Decimal('0.1')`` rather than the binary approximation
    ``Decimal('0.10000000000000000555...')``. This matters because API payloads
    decoded from JSON can contain floats.
    """
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        # str() gives the shortest representation that round-trips, which is
        # what the user actually meant when they typed the number.
        return Decimal(str(value))
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"مقدار عددی نامعتبر است: {value!r}") from exc


def quantize_money(value: Decimal | int | str | float) -> Decimal:
    """Round a monetary value to the storage precision.

    Uses ``ROUND_HALF_UP`` rather than Python's default banker's rounding so
    that 0.005 always rounds up, matching what a person expects when they see
    the number on screen.
    """
    return to_decimal(value).quantize(MONEY_PRECISION, rounding=ROUND_HALF_UP)


def sum_money(values) -> Decimal:
    """Sum an iterable of amounts, starting from an exact zero.

    ``sum()`` with a default start of ``0`` (int) works, but being explicit
    keeps the result a Decimal even for an empty iterable.
    """
    total = ZERO
    for value in values:
        total += to_decimal(value)
    return quantize_money(total)


def safe_divide(
    numerator: Decimal | int | float,
    denominator: Decimal | int | float,
    default: Decimal = ZERO,
) -> Decimal:
    """Divide, returning ``default`` when the denominator is zero.

    Every percentage in this app is ``part / whole``, and ``whole`` is
    legitimately zero whenever a user has not set a budget yet. Returning a
    sentinel rather than raising keeps the "no budget configured" case from
    becoming a 500 error.
    """
    denominator = to_decimal(denominator)
    if denominator == 0:
        return default
    return to_decimal(numerator) / denominator


def percentage(
    part: Decimal | int | float,
    whole: Decimal | int | float,
    *,
    default: Decimal = ZERO,
) -> Decimal:
    """Return ``part`` as a percentage of ``whole``, capped at 2 dp.

    Not capped at 100: overspending past a budget is real information and the
    UI needs to be able to say "۱۳۰٪ مصرف شده".
    """
    ratio = safe_divide(part, whole, default=default)
    return (ratio * 100).quantize(PERCENT_PRECISION, rounding=ROUND_HALF_UP)


def clamp(value: Decimal, low: Decimal, high: Decimal) -> Decimal:
    """Constrain ``value`` to the inclusive range ``[low, high]``."""
    return max(low, min(high, value))


def progress_ratio(part: Decimal | int | float, whole: Decimal | int | float) -> Decimal:
    """Fraction of a whole, clamped to ``0..1`` for progress-bar rendering."""
    ratio = safe_divide(part, whole)
    return clamp(ratio, Decimal("0"), Decimal("1"))
