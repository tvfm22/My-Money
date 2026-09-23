"""Which bank sent this message.

Two independent signals, deliberately
------------------------------------
A sender name is the strongest signal but the least reliable one: banks rotate
sender IDs, the same bank sends from short codes and alphanumeric IDs at the
same time, and a message forwarded or exported from a phone loses the sender
entirely. The body marker is weaker (a bank's name can appear inside another
bank's message) but survives a lost sender.

So detection tries the sender first, then the body, and reports ``unknown``
rather than guessing when neither is conclusive. An unknown bank is not an
error — the parse continues and the item is grouped as «بانک نامشخص» for the
user to classify. Guessing would silently attribute a figure to the wrong
account.

Where these tables came from
----------------------------
The sender hints and body markers below are taken from the message templates
used by public Iranian bank-SMS parsers (the PennywiseAI tracker's Iranian
parsers and the `ir_bank_sms_parser` Dart package) plus the templates documented
by the Iranian developer community for Melli, Sepah, Keshavarzi, Maskan, Saman,
blu and Bankino. They are *patterns to extend*, not a closed list: a bank that is
missing lands in ``unknown`` and stays importable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

UNKNOWN_CODE: Final = "unknown"
UNKNOWN_LABEL: Final = "بانک نامشخص"


@dataclass(frozen=True)
class BankRule:
    """How one bank is recognised.

    ``code`` is a stable slug used in stored rows and query parameters, so
    changing a display label never rewrites history. ``label`` is what the user
    sees, written in Persian like every other user-facing string.
    """

    code: str
    label: str
    sender_hints: tuple[str, ...]
    markers: tuple[str, ...]

    def marker_patterns(self) -> tuple[re.Pattern[str], ...]:
        return tuple(re.compile(marker) for marker in self.markers)


# Order is significant: the first rule that recognises the message wins. Digital
# banks and long names come first, because blu's templates quote its parent
# group's name in some wordings and "بانک مسکن" contains "مسکن".
BANK_RULES: tuple[BankRule, ...] = (
    BankRule(
        code="blubank",
        label="بلوبانک",
        # blu's sender IDs vary with no stable prefix (documented in the tracker's
        # blu parser), so several spellings are listed and the body marker is the
        # dependable half of the signal.
        sender_hints=("BLU", "9999987641", "98300087641"),
        markers=(r"بلو\s*بانک", r"بلوبانک", r"(?<![\w\u0600-\u06ff])بلو(?![\w\u0600-\u06ff])"),
    ),
    BankRule(
        code="bankino",
        label="بانکینو (خاورمیانه)",
        sender_hints=("BANKINO", "20004861"),
        markers=(r"بانک\s*خاورمیانه", r"بانکینو"),
    ),
    BankRule(
        code="saman",
        label="بانک سامان",
        sender_hints=("SAMAN",),
        markers=(r"بانک\s*سامان", r"(?<![\w\u0600-\u06ff])سامان(?![\w\u0600-\u06ff])"),
    ),
    BankRule(
        code="melli",
        label="بانک ملی",
        sender_hints=("MELLI", "98700717", "10001717"),
        markers=(r"بانک\s*ملی", r"(?<![\w\u0600-\u06ff])ملی(?![\w\u0600-\u06ff])"),
    ),
    BankRule(
        code="mellat",
        label="بانک ملت",
        sender_hints=("MELLAT", "MELAT"),
        markers=(r"بانک\s*ملت", r"(?<![\w\u0600-\u06ff])ملت(?![\w\u0600-\u06ff])"),
    ),
    BankRule(
        code="sepah",
        label="بانک سپه",
        sender_hints=("SEPAH",),
        markers=(r"بانک\s*سپه", r"(?<![\w\u0600-\u06ff])سپه(?![\w\u0600-\u06ff])"),
    ),
    BankRule(
        code="keshavarzi",
        label="بانک کشاورزی",
        sender_hints=("KESHAVARZI", "AGRIBANK"),
        markers=(r"بانک\s*کشاورزی", r"کشاورزی"),
    ),
    BankRule(
        code="maskan",
        label="بانک مسکن",
        sender_hints=("MASKAN",),
        markers=(r"بانک\s*مسکن", r"(?<![\w\u0600-\u06ff])مسکن(?![\w\u0600-\u06ff])"),
    ),
    BankRule(
        code="parsian",
        label="بانک پارسیان",
        sender_hints=("PARSIAN", "PERSIANBANK"),
        markers=(r"بانک\s*پارسیان", r"پارسیان"),
    ),
    BankRule(
        code="pasargad",
        label="بانک پاسارگاد",
        sender_hints=("PASARGAD",),
        markers=(r"بانک\s*پاسارگاد", r"پاسارگاد"),
    ),
    BankRule(
        code="tejarat",
        label="بانک تجارت",
        sender_hints=("TEJARAT",),
        markers=(r"بانک\s*تجارت",),
    ),
    BankRule(
        code="saderat",
        label="بانک صادرات",
        sender_hints=("SADERAT", "BSI"),
        markers=(r"بانک\s*صادرات", r"صادرات"),
    ),
    BankRule(
        code="refah",
        label="بانک رفاه",
        sender_hints=("REFAH",),
        markers=(r"بانک\s*رفاه",),
    ),
    BankRule(
        code="shahr",
        label="بانک شهر",
        sender_hints=("SHAHR", "CITYBANK"),
        markers=(r"بانک\s*شهر", r"شهر\s*بانک"),
    ),
    BankRule(
        code="sina",
        label="بانک سینا",
        sender_hints=("SINA",),
        markers=(r"بانک\s*سینا",),
    ),
    BankRule(
        code="ayandeh",
        label="بانک آینده",
        sender_hints=("AYANDEH",),
        markers=(r"بانک\s*آینده",),
    ),
    BankRule(
        code="eghtesad_novin",
        label="بانک اقتصاد نوین",
        sender_hints=("ENBANK", "EGHTESAD"),
        markers=(r"اقتصاد\s*نوین",),
    ),
    BankRule(
        code="resalat",
        label="بانک قرض‌الحسنه رسالت",
        sender_hints=("RESALAT",),
        markers=(r"رسالت",),
    ),
    BankRule(
        code="ghavamin",
        label="بانک قوامین",
        sender_hints=("GHAVAMIN",),
        markers=(r"قوامین",),
    ),
    BankRule(
        code="postbank",
        label="پست بانک",
        sender_hints=("POSTBANK",),
        markers=(r"پست\s*بانک",),
    ),
    BankRule(
        code="dey",
        label="بانک دی",
        sender_hints=("DEYBANK",),
        markers=(r"بانک\s*دی(?![\w\u0600-\u06ff])",),
    ),
    BankRule(
        code="mehr_iran",
        label="بانک قرض‌الحسنه مهر ایران",
        sender_hints=("MEHRIRAN",),
        markers=(r"مهر\s*ایران",),
    ),
    BankRule(
        code="sanat_madan",
        label="بانک صنعت و معدن",
        sender_hints=("SIMBANK",),
        markers=(r"صنعت\s*و\s*معدن",),
    ),
)


def _sender_upper(sender: str) -> str:
    """Uppercase a sender and strip the separators phone apps add."""
    return re.sub(r"[\s\-_]", "", (sender or "")).upper()


def detect_bank(text: str, sender: str = "") -> tuple[str, str]:
    """Return ``(code, label)`` for the bank behind a message.

    ``text`` must be the **normalized** body (see `normalize.normalize_text`),
    because the markers are matched literally against Persian spellings.
    """
    sender_key = _sender_upper(sender)

    if sender_key:
        for rule in BANK_RULES:
            for hint in rule.sender_hints:
                if re.sub(r"[\s\-_]", "", hint).upper() in sender_key:
                    return rule.code, rule.label

    if text:
        for rule in BANK_RULES:
            for pattern in rule.marker_patterns():
                if pattern.search(text):
                    return rule.code, rule.label

    return UNKNOWN_CODE, UNKNOWN_LABEL


def bank_label(code: str) -> str:
    """The Persian label for a stored bank code (``unknown`` included)."""
    for rule in BANK_RULES:
        if rule.code == code:
            return rule.label
    return UNKNOWN_LABEL

