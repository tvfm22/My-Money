"""The SMS parser: normalized text in, structured transaction out.

What it decides, and in what order
----------------------------------
1.  **Is this a transaction at all?** One-time passwords and advertising quote
    figures and would otherwise import as money.
2.  **Which bank?** From the sender, then from the body.
3.  **Direction**, from the ordered pattern table — sentence patterns first.
4.  **Balance**, as its own extraction step, independently of which direction
    pattern matched. A message's balance is a fact about the account, not about
    the wording of the sentence around the amount.
5.  **Amount**, attached to its own label (``مبلغ``) or, failing that, to the
    direction phrase.
6.  **Date**, Jalali first (that is what Iranian banks print), Gregorian next.
7.  **Confidence**, per field, plus a weighted overall score.

Two properties this module exists to guarantee
---------------------------------------------
*   The balance is attached by **proximity to its label**, never by position in
    the message. ``_extract_balance`` claims the span it used, and
    ``_extract_amount`` is then forbidden from reusing it — so "the first number
    is the amount, the second is the balance" is not a rule anywhere in here.
*   A missing balance produces ``None``, and costs only the balance field's own
    weight in the overall confidence. It is never zero, and never a warning.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from decimal import Decimal

from apps.core.jalali import to_gregorian

from .amounts import (
    DEFAULT_WINDOW,
    UNIT_UNKNOWN,
    AmountMatch,
    amount_near_label,
    candidates,
    find_amounts,
)
from .banks import bank_label, detect_bank
from .normalize import fingerprint, normalize_text
from .patterns import (
    AMOUNT_LABEL_COMPILED,
    BALANCE_COMPILED,
    CARD_COMPILED,
    CLOCK_PATTERN,
    DESCRIPTION_COMPILED,
    DIRECTION_COMPILED,
    GREGORIAN_DATE_PATTERN,
    JALALI_DATE_PATTERN,
    NON_TRANSACTION_COMPILED,
)

# Field weights for the overall score. They sum to 1.0 and the balance carries
# a tenth: a message with a direction, an amount and a date but no balance
# therefore scores 0.90, not 0.50 — "no balance printed" is a property of the
# template, not a parse failure.
CONFIDENCE_WEIGHTS: dict[str, Decimal] = {
    "direction": Decimal("0.30"),
    "amount": Decimal("0.30"),
    "date": Decimal("0.20"),
    "bank": Decimal("0.10"),
    "balance": Decimal("0.10"),
}

# Below this a parsed item is shown to the user as low confidence. It is *not* a
# rejection threshold: a doubtful row is still worth reviewing, whereas a
# silently dropped message is a transaction the user never learns about.
LOW_CONFIDENCE = Decimal("0.60")

_DATE_COMPILED = (
    ("jalali", re.compile(JALALI_DATE_PATTERN)),
    ("gregorian", re.compile(GREGORIAN_DATE_PATTERN)),
)
_CLOCK_COMPILED = re.compile(CLOCK_PATTERN)

_DIRECTION_LABELS = {"expense": "برداشت", "income": "واریز"}


@dataclass
class ParsedSms:
    """Everything one message yielded, including what it did not yield."""

    raw_text: str
    normalized: str = ""
    is_transaction: bool = True
    noise_kind: str = ""

    bank_code: str = "unknown"
    bank_label: str = ""
    sender: str = ""

    direction: str | None = None
    direction_pattern: str = ""
    direction_kind: str = ""

    amount_toman: Decimal | None = None
    amount_unit: str = UNIT_UNKNOWN
    amount_was_assumed: bool = False

    balance_after: Decimal | None = None
    balance_unit: str = UNIT_UNKNOWN
    balance_label: str = ""

    occurred_on: dt.date | None = None
    date_source: str = ""
    had_date_text: bool = False

    card_last4: str = ""
    merchant: str = ""
    description: str = ""

    confidence: Decimal = Decimal("0.000")
    field_confidence: dict[str, Decimal] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    fingerprint: str = ""

    @property
    def low_confidence(self) -> bool:
        return self.confidence < LOW_CONFIDENCE

    @property
    def is_usable(self) -> bool:
        """A transaction with a direction and an amount can be imported."""
        return self.is_transaction and bool(self.direction) and self.amount_toman is not None

    def to_dict(self) -> dict:
        """Plain-data view, for the preview endpoint and for tests."""
        return {
            "raw_text": self.raw_text,
            "bank": self.bank_code,
            "bank_label": self.bank_label,
            "sender": self.sender,
            "is_transaction": self.is_transaction,
            "noise_kind": self.noise_kind,
            "direction": self.direction,
            "direction_pattern": self.direction_pattern,
            "amount": str(self.amount_toman) if self.amount_toman is not None else None,
            "amount_unit": self.amount_unit,
            "amount_unit_assumed": self.amount_was_assumed,
            "balance_after": (
                str(self.balance_after) if self.balance_after is not None else None
            ),
            "balance_label": self.balance_label,
            "occurred_on": self.occurred_on.isoformat() if self.occurred_on else None,
            "date_source": self.date_source,
            "card_last4": self.card_last4,
            "merchant": self.merchant,
            "description": self.description,
            "confidence": str(self.confidence),
            "field_confidence": {
                key: str(value) for key, value in self.field_confidence.items()
            },
            "warnings": list(self.warnings),
            "fingerprint": self.fingerprint,
        }


# --------------------------------------------------------------------------
# Steps
# --------------------------------------------------------------------------


def _match_noise(text: str) -> str:
    """The kind of non-transaction this message is, or an empty string."""
    for kind, pattern in NON_TRANSACTION_COMPILED:
        if pattern.search(text):
            return kind
    return ""


def _direction_from_patterns(text: str) -> tuple[str | None, str, str, tuple[int, int] | None]:
    """First matching rule in the ordered table wins.

    Returns ``(direction, pattern_name, kind, span)``. The ordering of the table
    is what makes a sentence pattern beat the bare keyword inside it; see
    `patterns.py`.
    """
    for name, pattern, direction, kind in DIRECTION_COMPILED:
        match = pattern.search(text)
        if match:
            return direction, name, kind, (match.start(), match.end())
    return None, "", "", None


def _direction_from_sign(amounts: list[AmountMatch]) -> tuple[str | None, str, str, tuple[int, int] | None]:
    """Direction carried by a signed figure (Bankino's template).

    Consulted only when no word-based rule matched — a sign is the weakest
    signal here, because a minus sign also appears in balance arithmetic.
    """
    for amount in amounts:
        if amount.is_negative_sign:
            return "expense", "amount_sign_negative", "sign", (amount.start, amount.end)
        if amount.is_positive_sign:
            return "income", "amount_sign_positive", "sign", (amount.start, amount.end)
    return None, "", "", None


def _extract_balance(
    text: str, pool: list[AmountMatch]
) -> tuple[AmountMatch | None, str, tuple[int, int] | None]:
    """The ``balance_after`` figure: its own step, with its own label table.

    Every occurrence of every balance label is tried **in text order**, and the
    first one that actually has a figure attached to it wins. That handles a
    message which mentions "موجودی" in prose before the real "مانده حساب: ..."
    line without any special case.

    The figure must sit **after** its label (``allow_before=False``): a balance
    label followed by no figure is a dangling label — "…مبلغ 200,000 ریال کسر
    گردید. موجودی قابل برداشت" — and the figure in front of it is the
    transaction amount, not the balance. Promoting it would both put a wrong
    number in the reconciliation and starve the amount step; the backward rule
    stays available to the direction-phrase attachment, where the figure-first
    shape (blu Bank) is real.

    This runs before the transaction amount is chosen, and the span it used is
    handed to the amount step as "already claimed" — which is what prevents one
    number from silently filling both fields.
    """
    occurrences: list[tuple[int, int, str]] = []
    for _, pattern in BALANCE_COMPILED:
        for match in pattern.finditer(text):
            # Store the matched *text*, not the pattern: it is what the review
            # screen shows as the label the figure was read from ("مانده حساب").
            occurrences.append((match.start(), match.end(), match.group(0)))

    if not occurrences:
        return None, "", None

    # Text order, longest span first on a tie (a longer label match is the more
    # specific one).
    occurrences.sort(key=lambda item: (item[0], -(item[1] - item[0])))

    for start, end, label_text in occurrences:
        amount = amount_near_label(start, end, pool, allow_before=False)
        if amount is not None:
            return amount, label_text, (amount.start, amount.end)

    # A label with no figure near it: report the label, no number. Returning
    # `None` here is what makes "no balance in this message" produce a null
    # balance rather than a zero.
    return None, occurrences[0][2], None


def _extract_amount(
    text: str,
    pool: list[AmountMatch],
    claimed: tuple[tuple[int, int], ...],
    direction_span: tuple[int, int] | None,
) -> tuple[AmountMatch | None, str]:
    """The transaction figure, attached to its own label wherever one exists.

    Three attempts, in descending order of how much the message tells us:

    1.  **The amount label** (``مبلغ``). When a template says "مبلغ X ریال", X is
        the amount by definition, whatever else the message contains.
    2.  **The direction phrase.** blu Bank writes ``2,500,000 ریال از حساب شما
        پرید`` — the figure comes first and the phrase is its only context. The
        window is doubled here because a sentence can put a few words in between.
    3.  **The first unclaimed amount.** Melli's compact variants can print the
        figure with no label at all.

    ``claimed`` holds the balance's span. Every attempt respects it, which is
    the mechanism behind the "similar-looking figures" test: the balance is
    never eligible to be the amount, in any of the three attempts.
    """
    for _, pattern in AMOUNT_LABEL_COMPILED:
        match = pattern.search(text)
        if match is None:
            continue
        amount = amount_near_label(
            match.start(), match.end(), pool, exclude=claimed
        )
        if amount is not None:
            return amount, "amount_label"

    if direction_span is not None:
        amount = amount_near_label(
            direction_span[0],
            direction_span[1],
            pool,
            exclude=claimed,
            window=DEFAULT_WINDOW * 2,
        )
        if amount is not None:
            return amount, "direction_phrase"

    for amount in pool:
        if any(amount.overlaps(start, end) for start, end in claimed):
            continue
        return amount, "first_unclaimed"

    return None, ""


def _extract_date(text: str) -> tuple[dt.date | None, str, bool]:
    """``(date, source, had_date_text)``.

    Jalali is tried first because it is what Iranian bank templates print;
    Gregorian is accepted for the few English ones. A Jalali date is converted
    through `apps.core.jalali.to_gregorian`, the same converter the rest of the
    app uses to store and present dates, so the parser cannot disagree with the
    calendar the UI shows.
    """
    for source, pattern in _DATE_COMPILED:
        match = pattern.search(text)
        if match is None:
            continue

        try:
            year, month, day = (int(part) for part in match.groups())
        except (TypeError, ValueError):
            continue

        try:
            if source == "jalali":
                return to_gregorian(year, month, day), source, True
            return dt.date(year, month, day), source, True
        except ValueError:
            # A template can print something date-shaped that is not a date
            # (a reference number, a serial). Move on rather than fail.
            continue

    return None, "", False


def _extract_merchant(text: str, amounts: list[AmountMatch], stop_spans: tuple[tuple[int, int], ...]) -> str:
    """The merchant/description text a template carries, if any.

    The normalized text is a single line, so "the rest of the line" is not
    available. Instead the capture is cut at the next thing that is definitely
    not part of a merchant name: another figure, a balance label, or the unit
    word. A merchant name is short and sits immediately after its label, so a
    bounded window is enough — and whatever this produces is only a
    *suggestion* the user can edit before the transaction is created.
    """
    for _, pattern in DESCRIPTION_COMPILED:
        match = pattern.search(text)
        if match is None:
            continue

        start = match.end()
        while start < len(text) and text[start] in " :،,-\u2013\u2014\t":
            start += 1

        limit = min(start + MERCHANT_WINDOW, len(text))
        for span_start, _ in stop_spans:
            if start < span_start < limit:
                limit = span_start
        for amount in amounts:
            if start < amount.start < limit:
                limit = amount.start

        candidate = text[start:limit]
        # Cut any unit word that survived, then tidy the edges.
        candidate = re.split(r"(?:ریال|تومان|تومن)", candidate)[0]
        candidate = candidate.strip(" .,:،-")
        if len(candidate) < 2 or not any(char.isalpha() for char in candidate):
            continue
        return candidate[:120]

    return ""


# How far past a description label a merchant name may run.
MERCHANT_WINDOW = 60

_Q3 = Decimal("0.001")
_ONE = Decimal("1")

UNIT_ASSUMED_WARNING = (
    "واحد مبلغ در پیامک ذکر نشده بود؛ ریال در نظر گرفته شد. اگر مبلغ به تومان است، اصلاح کنید."
)
NO_DATE_WARNING = "تاریخی در پیامک پیدا نشد؛ تاریخ را خودتان تعیین کنید."
NO_DIRECTION_WARNING = "جهت تراکنش از متن پیامک مشخص نشد."
NO_AMOUNT_WARNING = "مبلغ تراکنش در متن پیامک پیدا نشد."
NO_BANK_WARNING = "بانک فرستنده شناسایی نشد؛ پیش از ثبت بررسی کنید."

_NOISE_WARNINGS = {
    "otp": "این پیامک کد یکبار مصرف است و تراکنش نیست.",
    "advertisement": "این پیامک تبلیغاتی است و تراکنش نیست.",
    "request": "این پیامک درخواست پرداخت است و تراکنش نیست.",
    "empty": "متن پیامک خالی است.",
}

_AMOUNT_SOURCE_SCORES = {
    "amount_label": Decimal("1.0"),
    "direction_phrase": Decimal("0.85"),
    "first_unclaimed": Decimal("0.7"),
}

_DIRECTION_KIND_SCORES = {
    "phrase": Decimal("1.0"),
    "keyword": Decimal("0.85"),
    "sign": Decimal("0.8"),
}

# What an assumed unit costs. It is a real risk — a Toman figure read as Rial is
# out by a factor of ten — but not a reason to reject the row.
UNIT_ASSUMED_PENALTY = Decimal("0.2")


def _score(
    *,
    direction_kind: str,
    amount_source: str,
    unit_assumed: bool,
    has_balance: bool,
    date_source: str,
    bank_code: str,
) -> tuple[Decimal, dict[str, Decimal]]:
    """Per-field confidence plus the weighted overall score.

    The per-field scores are what the review screen shows, because an overall
    "0.83" alone does not tell the user *what* to double-check. Each is derived
    from *how* the field was found, so the number has a meaning rather than
    being a vibe.
    """
    amount_score = _AMOUNT_SOURCE_SCORES.get(amount_source, Decimal("0"))
    if amount_score and unit_assumed:
        amount_score = max(amount_score - UNIT_ASSUMED_PENALTY, Decimal("0.3"))

    fields: dict[str, Decimal] = {
        "direction": _DIRECTION_KIND_SCORES.get(direction_kind, Decimal("0")),
        "amount": amount_score,
        "date": _ONE if date_source else Decimal("0"),
        "bank": _ONE if bank_code != "unknown" else Decimal("0.3"),
        "balance": _ONE if has_balance else Decimal("0"),
    }

    overall = sum(
        (CONFIDENCE_WEIGHTS[key] * value for key, value in fields.items()),
        Decimal("0"),
    )
    return overall.quantize(_Q3), {
        key: value.quantize(_Q3) for key, value in fields.items()
    }


def _extract_card_last4(text: str) -> str:
    """The card's last four digits, if the template prints them.

    Only used to enrich the suggested description ("خرید با کارت ۷۲۸۴") and to
    help the user recognise which card moved the money; it is never a field the
    parse depends on.
    """
    for pattern in CARD_COMPILED:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return ""


def _stop_spans(text: str) -> list[tuple[int, int]]:
    """Spans a merchant-name capture must not run past."""
    spans: list[tuple[int, int]] = []
    for _, pattern in BALANCE_COMPILED:
        spans.extend((match.start(), match.end()) for match in pattern.finditer(text))
    for _, pattern in AMOUNT_LABEL_COMPILED:
        spans.extend((match.start(), match.end()) for match in pattern.finditer(text))
    return spans


def parse_sms(raw_text: str, *, sender: str = "") -> ParsedSms:
    """Parse one message. Never raises on real input.

    Anything it cannot work out is left ``None`` and explained in ``warnings``; a
    message with no amount or no direction is still returned, so the user can
    see what arrived and classify it by hand. Silently dropping a message is the
    one outcome that would hide a real transaction.
    """
    raw = (raw_text or "").strip()
    result = ParsedSms(raw_text=raw, sender=(sender or "").strip())
    result.normalized = normalize_text(raw)
    result.fingerprint = fingerprint(raw)

    bank_code, detected_label = detect_bank(result.normalized, result.sender)
    result.bank_code = bank_code
    result.bank_label = detected_label

    if not result.normalized:
        result.is_transaction = False
        result.noise_kind = "empty"
        result.warnings.append(_NOISE_WARNINGS["empty"])
        result.confidence, result.field_confidence = _score(
            direction_kind="",
            amount_source="",
            unit_assumed=False,
            has_balance=False,
            date_source="",
            bank_code=bank_code,
        )
        return result

    noise_kind = _match_noise(result.normalized)
    if noise_kind:
        result.is_transaction = False
        result.noise_kind = noise_kind
        result.warnings.append(_NOISE_WARNINGS.get(noise_kind, ""))
        result.confidence, result.field_confidence = _score(
            direction_kind="",
            amount_source="",
            unit_assumed=False,
            has_balance=False,
            date_source="",
            bank_code=bank_code,
        )
        return result

    amounts = find_amounts(result.normalized)
    pool = candidates(amounts)

    direction, pattern_name, direction_kind, direction_span = _direction_from_patterns(
        result.normalized
    )
    if direction is None:
        direction, pattern_name, direction_kind, direction_span = _direction_from_sign(pool)

    # Balance first, then the amount — and the amount is told what the balance
    # already took. This order is what keeps two similar-looking figures in their
    # own fields.
    balance_amount, balance_label, balance_span = _extract_balance(result.normalized, pool)
    claimed = (balance_span,) if balance_span else ()
    amount, amount_source = _extract_amount(result.normalized, pool, claimed, direction_span)

    occurred_on, date_source, _ = _extract_date(result.normalized)

    stop_spans = _stop_spans(result.normalized)
    if direction_span:
        stop_spans.append(direction_span)
    if amount is not None:
        stop_spans.append((amount.start, amount.end))
    merchant = _extract_merchant(result.normalized, pool, tuple(stop_spans))

    card_last4 = _extract_card_last4(result.normalized)

    # --- Assign, with a warning for every field that could not be read ------
    result.direction = direction
    result.direction_pattern = pattern_name
    result.direction_kind = direction_kind
    if direction is None:
        result.warnings.append(NO_DIRECTION_WARNING)

    if amount is not None:
        result.amount_toman = amount.toman
        result.amount_unit = amount.unit
        result.amount_was_assumed = amount.unit_assumed
        if amount.unit_assumed:
            result.warnings.append(UNIT_ASSUMED_WARNING)
    else:
        result.warnings.append(NO_AMOUNT_WARNING)

    if balance_amount is not None:
        result.balance_after = balance_amount.toman
        result.balance_unit = balance_amount.unit
        result.balance_label = balance_label
    # No `else` on purpose: a message without a balance is completely normal
    # (most POS and transfer templates print none), so it is neither a warning
    # nor an error. `balance_after` stays None — never 0, which would read as an
    # empty account.

    result.occurred_on = occurred_on
    result.date_source = date_source
    if not date_source:
        result.warnings.append(NO_DATE_WARNING)

    if bank_code == "unknown":
        result.warnings.append(NO_BANK_WARNING)

    result.merchant = merchant
    result.card_last4 = card_last4

    label = _DIRECTION_LABELS.get(direction, "")
    fallback = " ".join(part for part in (label, result.bank_label) if part).strip()
    result.description = (merchant or fallback)[:200]

    result.confidence, result.field_confidence = _score(
        direction_kind=direction_kind,
        amount_source=amount_source,
        unit_assumed=bool(amount and amount.unit_assumed),
        has_balance=balance_amount is not None,
        date_source=date_source,
        bank_code=bank_code,
    )

    return result




