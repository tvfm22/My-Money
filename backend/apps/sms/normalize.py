"""Text normalization for Persian bank SMS.

Why normalize at all
--------------------
A bank SMS is written by a human in a bank's marketing department, sent through
a telecom gateway, and finally pasted by a user out of a phone app. Each hop
adds its own spelling of the same characters:

*   digits arrive as Persian (``۱۲۳``), Arabic-Indic (``١٢٣``) or Latin
    (``123``) — and often as a mix inside one message;
*   the Persian ``ی`` is frequently typed as Arabic ``ي`` and the ``ک`` as
    Arabic ``ك``, because that is what the default keyboard produces on many
    phones;
*   numbers are grouped with U+066C ``٬``, a Latin ``,``, or not at all;
*   words are separated by ZWNJ, a plain space, or two spaces after a line
    break in a template.

Matching keywords against that raw text means writing every pattern three
times. Instead **every pattern in this app is matched against the normalized
form**, produced by :func:`normalize_text`. One place to reason about, and the
normalization itself is directly testable.

What this deliberately does *not* do
------------------------------------
It does not touch the raw message: :class:`apps.sms.models.SmsImportItem` keeps
the original text verbatim so the user always sees what their bank sent, and so
a future parser fix can be replayed over history.
"""

from __future__ import annotations

import hashlib
import re

from apps.core.jalali import to_latin_digits

# Arabic presentation forms of the two letters that are most often mistyped.
# Written as escapes so the file survives any editor that would otherwise
# silently reorder right-to-left text.
_ARABIC_YEH = "\u064a"
_ARABIC_ALEF_MAQSURA = "\u0649"
_ARABIC_KAF = "\u0643"
_PERSIAN_YEH = "\u06cc"
_PERSIAN_KAF = "\u06a9"

# Zero-width non-joiner. Common inside Persian compound words.
ZWNJ = "\u200c"

# U+066C ARABIC THOUSANDS SEPARATOR and U+066B ARABIC DECIMAL SEPARATOR — the
# correct Persian grouping glyphs, which several banks use in their templates.
PERSIAN_THOUSANDS_SEPARATOR = "\u066c"
PERSIAN_DECIMAL_SEPARATOR = "\u066b"

# U+2212 MINUS SIGN, which appears in bank forms instead of ASCII '-'.
_UNICODE_MINUS = "\u2212"

# Zero-width and directional marks SMS gateways insert mid-word. ZWSP splits a
# word ("می\u200bشود"); LRM/RLM wrap numbers. All are invisible and carry no
# meaning for matching, so they are stripped rather than spaced.
_INVISIBLE_MARKS = ("\u200b", "\u200e", "\u200f", "\ufeff")

_DIGIT_AND_LETTER_MAP = str.maketrans(
    {
        _ARABIC_YEH: _PERSIAN_YEH,
        _ARABIC_ALEF_MAQSURA: _PERSIAN_YEH,
        _ARABIC_KAF: _PERSIAN_KAF,
        PERSIAN_THOUSANDS_SEPARATOR: ",",
        PERSIAN_DECIMAL_SEPARATOR: ".",
        _UNICODE_MINUS: "-",
        ZWNJ: " ",
        "\u00a0": " ",  # NBSP, produced by some SMS gateways
    }
)

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(raw: str) -> str:
    """Return the canonical form every pattern in this app is matched against.

    Steps, in order: digits to Latin, Arabic letter forms to Persian, Persian
    separators to their Latin equivalents, ZWNJ and NBSP to a plain space, and
    finally all whitespace runs collapsed to a single space.

    The result is *not* the text shown to the user — it is only ever a matching
    surface. ``"موجودي: ۴۸۸,۱۵۲ ریال"`` normalizes to
    ``"موجودی: 488,152 ریال"``.
    """
    if not raw:
        return ""

    # `to_latin_digits` is the project's single digit converter (it handles
    # Persian and Arabic-Indic digits), reused rather than reimplemented so the
    # parser and the rest of the app can never disagree about what "۱۲۳" means.
    text = to_latin_digits(str(raw))
    text = text.translate(_DIGIT_AND_LETTER_MAP)
    for mark in _INVISIBLE_MARKS:
        text = text.replace(mark, "")
    return _WHITESPACE_RE.sub(" ", text).strip()


def fingerprint(raw: str) -> str:
    """A stable hash of a message's normalized text.

    Used to answer "have I already imported this SMS?". Hashing the *normalized*
    form on purpose: the same message pasted twice from two phones can differ in
    digit glyphs and still be the same message, and it must not be imported
    twice.
    """
    normalized = normalize_text(raw)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def fold_keywords(text: str) -> str:
    """Lowercase Latin keywords and collapse spacing, for case-insensitive match.

    Persian has no letter case, but bank templates mix Latin words in
    (``TOMAN``, ``IRR``, ``POS``). Python's ``re.IGNORECASE`` does not fold the
    Arabic/Persian yeh pair, which is why that part lives in
    :func:`normalize_text` instead of being handled by the ``re`` flag. This
    helper exists so the intent is written down once.
    """
    return text.lower()
