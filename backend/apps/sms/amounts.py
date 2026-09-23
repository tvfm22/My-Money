"""Amount extraction — one implementation, shared by every money field.

The task this module exists for
-------------------------------
A bank SMS contains at least two numbers that both look like money: the
transaction amount and the balance after it. They are formatted identically, so
"the first number is the amount and the second is the balance" is not a rule —
it is a guess that breaks the moment a template prints the balance first (which
Saman and several others do) or mentions a fee, a reference number or a date.

So this module never answers "what is the amount". It answers **"what amounts
appear, and where"** — :class:`AmountMatch` carries the character span of every
candidate — and the parser then attaches each one to the field whose *label* it
sits next to. Attachment by proximity to a label is the property the tests pin
down.

One amount parser, two consumers
--------------------------------
Transaction amount and balance both go through :func:`amount_near_label`. The
requirement was explicit that the balance must not grow a second, subtly
different number parser: comma normalization, Persian digits, and the
rial/toman distinction all live here alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from apps.core.money import quantize_money

# --- Units -----------------------------------------------------------------

RIAL = "rial"
TOMAN = "toman"
UNIT_UNKNOWN = ""

# Ten Rial to one Toman, fixed since 1932 and the only rate that ever applies
# here: the two are the same currency at two scales, not two currencies.
RIAL_PER_TOMAN = Decimal("10")

_UNIT_WORDS = {
    "ریال": RIAL,
    "ريال": RIAL,  # Arabic yeh, still possible before normalization
    "IRR": RIAL,
    "RIAL": RIAL,
    "تومان": TOMAN,
    "تومن": TOMAN,  # colloquial spelling, used by blu Bank
    "TOMAN": TOMAN,
}

# A number, optionally grouped with commas, optionally with a decimal part.
# Grouping is validated (`1,23,456` is not an amount) because a sloppy regex
# here would happily read a card number as money.
_NUMBER = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"

# The signed form is not decoration: Bankino's template communicates direction
# *only* through the sign, so it has to be captured.
_AMOUNT_RE = re.compile(
    rf"(?P<sign>[+-])?\s*(?P<number>{_NUMBER})\s*(?P<unit>[A-Za-z\u0600-\u06ff]{{0,6}})?"
)

# A run of digits this long with no separators is a card, account, reference or
# phone number — never an amount. Iranian card numbers are 16 digits and
# IBAN-style account numbers are 22.
_LONG_DIGIT_RUN = 9

# Short identifiers that also look like money. "کارت 7284" is a card suffix and
# "شماره پیگیری 45812" a tracking code; both are 4-5 digit numbers that pass the
# length check, and reading either as a balance would be a wrong number in the
# user's ledger rather than a missing one.
_IDENTIFIER_PREFIX_RE = re.compile(
    r"(?:کارت|شماره\s*کارت|شماره\s*حساب|شماره\s*پیگیری|شماره\s*تراکنش|شماره\s*سند|"
    r"کد\s*رهگیری|کد\s*پیگیری|شناسه|پیگیری|مرجع)[\s:*]*$"
)

# How far back the identifier prefix is looked for.
_IDENTIFIER_LOOKBEHIND = 24


# Separators that mean "this digit group is part of a date or a clock time".
_DATE_SEPARATORS = "/-.:"

# How far from a label a number may sit and still belong to it. Room for
# "موجودی حساب: 12,345,678 ریال", and for the figure landing on the next line of
# a multi-line template, which is exactly the shape the SMS variants use.
DEFAULT_WINDOW = 40


@dataclass(frozen=True)
class AmountMatch:
    """One numeric amount found in a message, with the span it occupies.

    ``value`` is what the message literally said; ``toman`` is that value in the
    app's storage unit. Keeping both means a warning can be raised about the
    unit without losing the original figure.
    """

    start: int
    end: int
    text: str
    value: Decimal
    unit: str
    sign: str = ""

    @property
    def unit_assumed(self) -> bool:
        """True when the message named no unit and Rial had to be assumed."""
        return self.unit == UNIT_UNKNOWN

    @property
    def toman(self) -> Decimal:
        """The value in Toman, the unit this app stores."""
        return to_toman(self.value, self.unit)

    @property
    def is_positive_sign(self) -> bool:
        return self.sign == "+"

    @property
    def is_negative_sign(self) -> bool:
        return self.sign == "-"

    def overlaps(self, start: int, end: int) -> bool:
        """True when this amount's span intersects ``[start, end)``."""
        return self.start < end and start < self.end


def to_toman(value: Decimal, unit: str) -> Decimal:
    """Convert a value tagged with an explicit unit into Toman.

    A message that named no unit is treated as Rial: every Iranian bank quotes
    Rial when it omits the word, and a Toman figure without the word would be a
    hundred times smaller than what the account actually moved. The assumption
    is recorded on the match (``unit_assumed``) so it costs confidence rather
    than passing silently.
    """
    if unit == TOMAN:
        return quantize_money(value)
    return quantize_money(value / RIAL_PER_TOMAN)


def parse_amount_text(text: str) -> Decimal | None:
    """Parse a single amount string (``"1,500,000"``) into a ``Decimal``.

    Used when a user corrects a figure by hand, so a manual edit goes through
    the same normalization as an automatic read instead of a second code path.
    """
    cleaned = re.sub(r"[,\s]", "", (text or "").strip())
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except Exception:  # noqa: BLE001 - malformed input simply means "no amount"
        return None


def _long_digit_run_spans(text: str) -> list[tuple[int, int]]:
    """Spans of digit runs long enough to be an identifier rather than money."""
    return [
        (match.start(), match.end())
        for match in re.finditer(r"\d+", text)
        if len(match.group(0)) >= _LONG_DIGIT_RUN
    ]


def _touches_date_separator(text: str, start: int, end: int) -> bool:
    """True when the number is a component of a date or a clock time.

    ``1405/03/22`` yields three numbers and ``07:28`` two; none is money. A
    separator alone is not enough to disqualify a figure, so the check also
    requires a digit on the far side of the separator — that is what keeps
    ``1,000,000`` (grouped, all money) apart from ``1405/03`` (a date).
    """
    before = text[start - 1] if start > 0 else ""
    after = text[end] if end < len(text) else ""
    neighbour = text[start - 2] if start > 1 else ""
    following = text[end + 1] if end + 1 < len(text) else ""

    if before in _DATE_SEPARATORS and neighbour.isdigit():
        return True
    if after in _DATE_SEPARATORS and following.isdigit():
        return True
    return False


def find_amounts(text: str) -> list[AmountMatch]:
    """Every monetary-looking amount in a **normalized** message, in order.

    Deliberately permissive: it reports candidates, including ones a later step
    discards. Filtering here would make the parser's decisions invisible, and a
    message that yielded nothing would give no clue why.
    """
    if not text:
        return []

    identifier_spans = _long_digit_run_spans(text)
    amounts: list[AmountMatch] = []

    for match in _AMOUNT_RE.finditer(text):
        start, end = match.span("number")

        # Inside an identifier (card number, reference code, phone): not money.
        if any(start < span_end and span_start < end for span_start, span_end in identifier_spans):
            continue
        # Prefixed by an identifier word ("کارت 7284", "کد رهگیری 45812").
        if _IDENTIFIER_PREFIX_RE.search(text[max(0, start - _IDENTIFIER_LOOKBEHIND) : start]):
            continue
        if _touches_date_separator(text, start, end):
            continue

        value = parse_amount_text(match.group("number"))
        if value is None:
            continue

        unit_raw = (match.group("unit") or "").strip()
        unit = _UNIT_WORDS.get(unit_raw.upper(), _UNIT_WORDS.get(unit_raw, UNIT_UNKNOWN))

        # The unit word must start immediately after the number to belong to it;
        # `_AMOUNT_RE` enforces that by consuming at most the next word.
        amounts.append(
            AmountMatch(
                start=start,
                end=end,
                text=match.group(0).strip(),
                value=value,
                unit=unit,
                sign=match.group("sign") or "",
            )
        )

    return amounts


# Below this a figure is a counter or a template artefact rather than money.
# 100 Toman — low enough for a real small purchase, high enough to reject a
# bare "1" or a page number.
MIN_AMOUNT_TOMAN = Decimal("100")


def candidates(amounts: list[AmountMatch]) -> list[AmountMatch]:
    """Keep only amounts that could be a transaction or a balance figure.

    A signed amount is always kept even when small, because the sign is
    direction information (Bankino) and `-500` is not a typo.
    """
    return [
        amount
        for amount in amounts
        if amount.sign or amount.toman >= MIN_AMOUNT_TOMAN
    ]


def amount_near_label(
    label_start: int,
    label_end: int,
    amounts: list[AmountMatch],
    *,
    exclude: tuple[tuple[int, int], ...] = (),
    window: int = DEFAULT_WINDOW,
    allow_before: bool = True,
) -> AmountMatch | None:
    """The amount that belongs to the label spanning ``[label_start, label_end)``.

    Selection order, and the reasoning for it:

    1.  **Nearest amount after the label, within ``window``.** Every template
        this app supports prints the figure after its label — ``موجودی: 488,152
        ریال``. This is the common case, so it is decided first.
    2.  **Nearest amount before the label, within ``window``** — only when
        ``allow_before`` is set. Some attachments put the figure first and the
        context after it (blu Bank's ``2,500,000 ریال از حساب شما پرید``), so
        the direction-phrase attachment needs this; it is a real shape there.
        The *balance* attachment passes ``allow_before=False``: a balance label
        followed by no figure is a dangling label, and the figure in front of it
        is the transaction amount — silently promoting it to the balance would
        put a wrong number in the user's reconciliation, which is worse than a
        null balance.
    3.  **Nothing.** Returning ``None`` is a valid answer and an important one: a
        message with no balance must produce a null balance, never a zero.

    ``exclude`` carries spans already claimed by another field, which is what
    makes it impossible for one number to be both the amount and the balance.
    """

    def claimed(amount: AmountMatch) -> bool:
        return any(amount.overlaps(start, end) for start, end in exclude)

    pool = [amount for amount in amounts if not claimed(amount)]

    after = [
        amount
        for amount in pool
        if amount.start >= label_end and (amount.start - label_end) <= window
    ]
    if after:
        return min(after, key=lambda amount: amount.start)

    if not allow_before:
        return None

    before = [
        amount
        for amount in pool
        if amount.end <= label_start and (label_start - amount.end) <= window
    ]
    if before:
        return max(before, key=lambda amount: amount.end)

    return None
