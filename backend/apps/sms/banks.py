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
        # Case-insensitive: bodies mix "Saman Bank", "SAMAN" and "بانک سامان".
        return tuple(re.compile(marker, re.IGNORECASE) for marker in self.markers)


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
        sender_hints=("BLU", "BLUBANK", "9999987641", "98300087641", "بلو", "بلوبانک"),
        markers=(
            r"بلو\s*بانک",
            r"بلوبانک",
            r"Blu\s*Bank",
            r"(?<![\w\u0600-\u06ff])بلو(?![\w\u0600-\u06ff])",
        ),
    ),
    BankRule(
        code="bankino",
        label="بانکینو (خاورمیانه)",
        sender_hints=("BANKINO", "20004861", "بانکینو", "خاورمیانه"),
        markers=(
            r"بانک\s*خاورمیانه",
            r"بانکینو",
            r"خاورمیانه",
            r"Middle\s*East\s*Bank",
        ),
    ),
    BankRule(
        code="saman",
        label="بانک سامان",
        sender_hints=("SAMAN", "SAMANBANK", "BANKSAMAN", "200044", "بانک سامان", "سامان"),
        markers=(
            r"بانک\s*سامان",
            r"Saman\s*Bank",
            r"Bank\s*Saman",
            r"(?<![\w\u0600-\u06ff])سامان(?![\w\u0600-\u06ff])",
        ),
    ),
    BankRule(
        code="melli",
        label="بانک ملی",
        sender_hints=(
            "MELLI",
            "MELLIBANK",
            "BANKMELLI",
            "BMI",
            "98700717",
            "10001717",
            "بانک ملی",
        ),
        markers=(
            r"بانک\s*ملی",
            r"Bank\s*Melli",
            r"Melli\s*Bank",
            r"(?<![\w\u0600-\u06ff])ملی(?![\w\u0600-\u06ff])",
        ),
    ),
    BankRule(
        code="mellat",
        label="بانک ملت",
        sender_hints=(
            "MELLAT",
            "MELAT",
            "MELLATBANK",
            "BANKMELLAT",
            "200033",
            "300033",
            "بانک ملت",
        ),
        markers=(
            r"بانک\s*ملت",
            r"Bank\s*Mellat",
            r"Mellat\s*Bank",
            r"(?<![\w\u0600-\u06ff])ملت(?![\w\u0600-\u06ff])",
        ),
    ),
    BankRule(
        code="sepah",
        label="بانک سپه",
        sender_hints=("SEPAH", "SEPAHBANK", "BANKSEPAH", "200020", "بانک سپه"),
        markers=(
            r"بانک\s*سپه",
            r"Bank\s*Sepah",
            r"Sepah\s*Bank",
            r"(?<![\w\u0600-\u06ff])سپه(?![\w\u0600-\u06ff])",
        ),
    ),
    BankRule(
        code="keshavarzi",
        label="بانک کشاورزی",
        sender_hints=(
            "KESHAVARZI",
            "AGRIBANK",
            "AGRI",
            "200091",
            "300091",
            "بانک کشاورزی",
        ),
        markers=(
            r"بانک\s*کشاورزی",
            r"کشاورزی",
            r"Keshavarzi",
            r"Agri\s*Bank",
        ),
    ),
    BankRule(
        code="maskan",
        label="بانک مسکن",
        sender_hints=("MASKAN", "MASKANBANK", "BANKMASKAN", "100090", "بانک مسکن"),
        markers=(
            r"بانک\s*مسکن",
            r"Maskan\s*Bank",
            r"Bank\s*Maskan",
            r"(?<![\w\u0600-\u06ff])مسکن(?![\w\u0600-\u06ff])",
        ),
    ),
    BankRule(
        code="parsian",
        label="بانک پارسیان",
        sender_hints=("PARSIAN", "PERSIANBANK", "PARSIANBANK", "بانک پارسیان"),
        markers=(
            r"بانک\s*پارسیان",
            r"پارسیان",
            r"Parsian\s*Bank",
        ),
    ),
    BankRule(
        code="pasargad",
        label="بانک پاسارگاد",
        sender_hints=("PASARGAD", "PASARGADBANK", "BANKPASARGAD", "بانک پاسارگاد"),
        markers=(
            r"بانک\s*پاسارگاد",
            r"پاسارگاد",
            r"Pasargad\s*Bank",
        ),
    ),
    BankRule(
        code="tejarat",
        label="بانک تجارت",
        sender_hints=("TEJARAT", "TEJARATBANK", "BANKTEJARAT", "200044", "بانک تجارت"),
        markers=(
            r"بانک\s*تجارت",
            r"تجارت",
            r"Tejarat\s*Bank",
        ),
    ),
    BankRule(
        code="saderat",
        label="بانک صادرات",
        sender_hints=("SADERAT", "BSI", "SADERATBANK", "300013", "بانک صادرات"),
        markers=(
            r"بانک\s*صادرات",
            r"صادرات",
            r"Saderat\s*Bank",
            r"\bBSI\b",
        ),
    ),
    BankRule(
        code="refah",
        label="بانک رفاه",
        sender_hints=("REFAH", "REFAHBANK", "BANKREFAH", "200040", "بانک رفاه"),
        markers=(
            r"بانک\s*رفاه",
            r"رفاه\s*کارگران",
            r"Refah\s*Bank",
        ),
    ),
    BankRule(
        code="shahr",
        label="بانک شهر",
        sender_hints=("SHAHR", "CITYBANK", "SHAHRBANK", "200048", "بانک شهر"),
        markers=(
            r"بانک\s*شهر",
            r"شهر\s*بانک",
            r"Shahr\s*Bank",
            r"City\s*Bank",
        ),
    ),
    BankRule(
        code="sina",
        label="بانک سینا",
        sender_hints=("SINA", "SINABANK", "BANKSINA", "بانک سینا"),
        markers=(
            r"بانک\s*سینا",
            r"سینا",
            r"Sina\s*Bank",
        ),
    ),
    BankRule(
        code="ayandeh",
        label="بانک آینده",
        sender_hints=("AYANDEH", "AYANDEHBANK", "300062", "بانک آینده"),
        markers=(
            r"بانک\s*آینده",
            r"آینده",
            r"Ayandeh\s*Bank",
        ),
    ),
    BankRule(
        code="eghtesad_novin",
        label="بانک اقتصاد نوین",
        sender_hints=("ENBANK", "EGHTESAD", "ENB", "بانک اقتصاد نوین", "اقتصاد نوین"),
        markers=(
            r"اقتصاد\s*نوین",
            r"Eghtesad\s*Novin",
        ),
    ),
    BankRule(
        code="karafarin",
        label="بانک کارآفرین",
        sender_hints=("KARAFARIN", "KARAFARINBANK", "بانک کارآفرین", "کارآفرین"),
        markers=(
            r"بانک\s*کارآفرین",
            r"کارآفرین",
            r"Karafarin\s*Bank",
        ),
    ),
    BankRule(
        code="gardeshgari",
        label="بانک گردشگری",
        sender_hints=("GARDESHGARI", "TOURISMBANK", "بانک گردشگری", "گردشگری"),
        markers=(
            r"بانک\s*گردشگری",
            r"گردشگری",
            r"Tourism\s*Bank",
        ),
    ),
    BankRule(
        code="sarmayeh",
        label="بانک سرمایه",
        sender_hints=("SARMAYEH", "SARMAYEBANK", "بانک سرمایه"),
        markers=(
            r"بانک\s*سرمایه",
            r"Sarmayeh\s*Bank",
        ),
    ),
    BankRule(
        code="iranzamin",
        label="بانک ایران زمین",
        sender_hints=("IRANZAMIN", "IZBANK", "بانک ایران زمین", "ایران زمین"),
        markers=(
            r"بانک\s*ایران\s*زمین",
            r"ایران\s*زمین",
            r"Iran\s*Zamin",
        ),
    ),
    BankRule(
        code="tosee_taavon",
        label="بانک توسعه تعاون",
        sender_hints=("TAAVON", "TAAVONBANK", "TTBANK", "بانک توسعه تعاون", "توسعه تعاون"),
        markers=(
            r"توسعه\s*تعاون",
            r"Tosee\s*Taavon",
        ),
    ),
    BankRule(
        code="sanat_madan",
        label="بانک صنعت و معدن",
        sender_hints=("SIMBANK", "BIM", "بانک صنعت و معدن", "صنعت و معدن"),
        markers=(
            r"صنعت\s*و\s*معدن",
            r"Sanat\s*Madan",
        ),
    ),
    BankRule(
        code="tosee_saderat",
        label="بانک توسعه صادرات",
        sender_hints=("EDBI", "توسعه صادرات", "بانک توسعه صادرات"),
        markers=(r"توسعه\s*صادرات",),
    ),
    BankRule(
        code="resalat",
        label="بانک قرض‌الحسنه رسالت",
        sender_hints=("RESALAT", "RQ", "بانک رسالت", "رسالت"),
        markers=(
            r"بانک\s*رسالت",
            r"قرض\s*الحسنه\s*رسالت",
            r"رسالت",
        ),
    ),
    BankRule(
        code="mehr_iran",
        label="بانک قرض‌الحسنه مهر ایران",
        sender_hints=("MEHRIRAN", "MEHR", "QMB", "بانک مهر ایران", "مهر ایران"),
        markers=(
            r"بانک\s*مهر\s*ایران",
            r"مهر\s*ایران",
            r"Mehr\s*Iran",
        ),
    ),
    BankRule(
        code="ghavamin",
        label="بانک قوامین",
        sender_hints=("GHAVAMIN", "بانک قوامین"),
        markers=(r"قوامین",),
    ),
    BankRule(
        code="hekmat",
        label="بانک حکمت ایرانیان",
        sender_hints=("HEKMAT", "بانک حکمت", "حکمت ایرانیان"),
        markers=(
            r"بانک\s*حکمت",
            r"حکمت\s*ایرانیان",
        ),
    ),
    BankRule(
        code="noor",
        label="بانک نور",
        sender_hints=("NOORBANK", "بانک نور"),
        markers=(r"بانک\s*نور",),
    ),
    BankRule(
        code="middle_east",
        label="بانک خاورمیانه",
        sender_hints=("MIDDLEEAST", "MEBANK"),
        markers=(r"Middle\s*East\s*Bank",),
    ),
    BankRule(
        code="postbank",
        label="پست بانک",
        sender_hints=("POSTBANK", "PBI", "پست بانک"),
        markers=(
            r"پست\s*بانک",
            r"Post\s*Bank",
        ),
    ),
    BankRule(
        code="dey",
        label="بانک دی",
        sender_hints=("DEYBANK", "DAYBANK", "DEY", "بانک دی"),
        markers=(
            r"بانک\s*دی(?![\w\u0600-\u06ff])",
            r"Day\s*Bank",
            r"Dey\s*Bank",
        ),
    ),
    BankRule(
        code="melal",
        label="بانک ملل",
        sender_hints=("MELAL", "MELALBANK", "بانک ملل"),
        markers=(
            r"بانک\s*ملل",
            r"موسسه\s*ملل",
            r"Melal\s*Bank",
        ),
    ),
    BankRule(
        code="hamrahcard",
        label="همراه‌کارت",
        sender_hints=("HAMRAHCARD", "همراه کارت", "همراه‌کارت"),
        markers=(r"همراه\s*کارت",),
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

