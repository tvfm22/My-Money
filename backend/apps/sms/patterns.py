"""Pattern tables: direction, balance labels, amount anchors, noise.

Why the tables live apart from the parser
-----------------------------------------
The parser's *logic* (how a figure is attached to a field) has been stable since
the first bank; the *vocabulary* has not. Banks reword their templates, new
banks get added, and a user forwards a message from a bank nobody listed. Every
one of those changes is an edit to a table in this file plus a line of test data
— never a change to control flow.

Match order is data, not code
-----------------------------
``DIRECTION_PATTERNS`` is an **ordered** tuple and the parser takes the first
match. Sentence patterns are therefore assembled before keyword patterns, as a
structural guarantee rather than by hoping nobody reorders a list:

    "از حساب شما مبلغ 5,000,000 ریال کسر گردید. موجودی: ..."

contains an expense phrase, while a hypothetical
``"برداشت پول ... به حساب شما واریز گردید"`` contains a debit keyword *and* a
credit phrase. First-match-wins over an ordered table resolves that
deterministically and visibly. A dict of keywords would resolve it by whichever
branch was written first, which is how the wrong direction ships.

Specific-before-generic is the rule for anything added here:

1.  full sentence patterns (``از حساب ... کسر گردید``);
2.  bank-specific phrasings (blu Bank's ``از حساب شما پرید``);
3.  the accounting tags (``بدهکار`` / ``بستانکار``);
4.  bare keywords (``برداشت``, ``واریز``) last, as the fallback.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from .amounts import RIAL, TOMAN

EXPENSE: Final = "expense"
INCOME: Final = "income"


@dataclass(frozen=True)
class DirectionPattern:
    """One rule that reads a transaction's direction out of a message.

    ``name`` exists so a parsed item records *which* rule fired. When a message
    is classified wrongly, the first question is which pattern claimed it, and a
    stored name answers that without re-running the parser by hand.
    """

    name: str
    pattern: str
    direction: str
    # "phrase" rules are full sentences, "keyword" rules are single words. Used
    # for the stored record and to keep the table readable; the ordering above
    # is what actually decides a conflict.
    kind: str = "phrase"

    def compile(self) -> re.Pattern[str]:
        # Case-insensitive for the English templates ("Withdrawal", "Balance",
        # "Amount"); Persian has no letter case, so this changes nothing there.
        return re.compile(self.pattern, re.IGNORECASE)


# --------------------------------------------------------------------------
# 1. Sentence patterns — expense
# --------------------------------------------------------------------------
# "از حساب شما مبلغ ... ریال کسر گردید." — Sepah, Keshavarzi, Maskan and Saman
# all phrase a withdrawal this way. The optional "شما" is what makes one rule
# cover the retail and the corporate wording.
_EXPENSE_SENTENCE_PATTERNS: tuple[DirectionPattern, ...] = (
    DirectionPattern(
        name="debit_sentence_kasr",
        pattern=r"از\s*حساب(?:\s*شما)?.*?کسر\s*(?:گردید|شد|شده)",
        direction=EXPENSE,
    ),
    DirectionPattern(
        name="debit_sentence_kasr_az_hesab",
        pattern=r"کسر\s*از\s*حساب",
        direction=EXPENSE,
    ),
    DirectionPattern(
        name="debit_sentence_bardasht",
        pattern=r"از\s*حساب(?:\s*شما)?.*?برداشت\s*(?:گردید|شد|شده)",
        direction=EXPENSE,
    ),
    DirectionPattern(
        name="debit_sentence_bardasht_az_hesab",
        pattern=r"برداشت\s*از\s*حساب",
        direction=EXPENSE,
    ),
    DirectionPattern(
        name="debit_sentence_bardasht_az_kart",
        pattern=r"برداشت\s*از\s*کارت",
        direction=EXPENSE,
    ),
    DirectionPattern(
        name="debit_sentence_pardakht_az_hesab",
        pattern=r"پرداخت\s*از\s*حساب",
        direction=EXPENSE,
    ),
    DirectionPattern(
        name="debit_sentence_kharid_az_hesab",
        pattern=r"خرید\s*از\s*حساب",
        direction=EXPENSE,
    ),
    DirectionPattern(
        name="debit_sentence_kharid_ba_kart",
        pattern=r"خرید\s*(?:با\s*کارت|اینترنتی)",
        direction=EXPENSE,
    ),
    DirectionPattern(
        name="debit_sentence_pardakht_ghabz",
        pattern=r"پرداخت\s*(?:قبض|قسط|صورت\s*حساب)",
        direction=EXPENSE,
    ),
    DirectionPattern(
        name="debit_sentence_bedehkar_shod",
        pattern=r"حساب(?:\s*شما)?.*?بدهکار\s*(?:شد|گردید)",
        direction=EXPENSE,
    ),
    DirectionPattern(
        name="debit_sentence_be_mablagh_bedehkar",
        pattern=r"به\s*مبلغ.*?بدهکار\s*(?:شد|گردید)",
        direction=EXPENSE,
    ),
    DirectionPattern(
        name="debit_sentence_bardasht_vajh",
        pattern=r"برداشت\s*وجه(?:\s*نقد)?",
        direction=EXPENSE,
    ),
    DirectionPattern(
        name="debit_sentence_enteghal_vajh",
        pattern=r"انتقال\s*وجه",
        direction=EXPENSE,
    ),
    DirectionPattern(
        name="debit_sentence_havaleh_az",
        pattern=r"حواله\s*(?:از\s*حساب|صادره)",
        direction=EXPENSE,
    ),
    DirectionPattern(
        name="debit_sentence_kart_be_kart",
        pattern=r"کارت\s*به\s*کارت.*?از\s*کارت",
        direction=EXPENSE,
    ),
    # "انتقال از حساب" / "انتقال به حساب" are both outgoing: money leaves the
    # account the message is about. Two rules rather than one because the span
    # they match differs and the recorded pattern name should say which.
    DirectionPattern(
        name="debit_sentence_transfer_from",
        pattern=r"انتقال\s*(?:از|به)\s*حساب",
        direction=EXPENSE,
    ),
    DirectionPattern(name="debit_transfer_to", pattern=r"انتقال\s*به", direction=EXPENSE),
    DirectionPattern(
        name="debit_sentence_transfer_az_kart",
        pattern=r"انتقال\s*از\s*کارت",
        direction=EXPENSE,
    ),
    # blu Bank's sentence-shaped debit. Colloquial on purpose — this is the
    # literal template, not a guess at one.
    DirectionPattern(
        name="debit_blu_perid",
        pattern=r"از\s*حساب\s*شما\s*پرید",
        direction=EXPENSE,
    ),
)


# --------------------------------------------------------------------------
# 2. Sentence patterns — credit
# --------------------------------------------------------------------------
_CREDIT_SENTENCE_PATTERNS: tuple[DirectionPattern, ...] = (
    DirectionPattern(
        name="credit_sentence_variz",
        pattern=r"به\s*حساب(?:\s*شما)?.*?واریز\s*(?:گردید|شد|شده)",
        direction=INCOME,
    ),
    # Bank Melli puts the same words the other way round: "واریز به حساب شما
    # انجام شد". Same meaning, different order — which is exactly why the table
    # is phrase-level rather than word-level.
    DirectionPattern(
        name="credit_sentence_variz_be_hesab",
        pattern=r"واریز\s*به\s*حساب(?:\s*شما)?.*?(?:انجام\s*شد|گردید|شد)",
        direction=INCOME,
    ),
    DirectionPattern(
        name="credit_blu_neshast",
        pattern=r"به\s*حساب\s*شما\s*نشست",
        direction=INCOME,
    ),
    DirectionPattern(
        name="credit_sentence_variz_az",
        pattern=r"واریز\s*(?:از\s*طریق|از\s*حساب|به\s*حساب)",
        direction=INCOME,
    ),
    DirectionPattern(
        name="credit_sentence_bestankar_shod",
        pattern=r"حساب(?:\s*شما)?.*?بستانکار\s*(?:شد|گردید)",
        direction=INCOME,
    ),
    DirectionPattern(
        name="credit_sentence_be_mablagh_bestankar",
        pattern=r"به\s*مبلغ.*?بستانکار\s*(?:شد|گردید)",
        direction=INCOME,
    ),
    DirectionPattern(
        name="credit_sentence_daryaft_vajh",
        pattern=r"دریافت\s*(?:وجه|مبلغ|حواله)",
        direction=INCOME,
    ),
    DirectionPattern(
        name="credit_sentence_variz_hoghugh",
        pattern=r"واریز\s*(?:حقوق|یارانه|سود|عیدی|پاداش|مستمری)",
        direction=INCOME,
    ),
    DirectionPattern(
        name="credit_sentence_havaleh_be",
        pattern=r"حواله\s*(?:به\s*حساب|وارده|دریافتی)",
        direction=INCOME,
    ),
    DirectionPattern(
        name="credit_sentence_enteghal_be_shoma",
        pattern=r"انتقال\s*به\s*حساب\s*شما",
        direction=INCOME,
    ),
    DirectionPattern(
        name="credit_sentence_sharj_shod",
        pattern=r"حساب(?:\s*شما)?\s*شارژ\s*(?:شد|گردید)",
        direction=INCOME,
    ),
)


# --------------------------------------------------------------------------
# 3. Accounting tags
# --------------------------------------------------------------------------
# "بستانکار" / "بدهکار" are how older and corporate templates state direction.
_TAG_PATTERNS: tuple[DirectionPattern, ...] = (
    DirectionPattern(name="credit_bestankar", pattern=r"بستانکار", direction=INCOME, kind="keyword"),
    DirectionPattern(name="debit_bedehkar", pattern=r"بدهکار", direction=EXPENSE, kind="keyword"),
)


# --------------------------------------------------------------------------
# 4. Bare keywords — the fallback, deliberately last
# --------------------------------------------------------------------------
_KEYWORD_PATTERNS: tuple[DirectionPattern, ...] = (
    # Longer phrases first inside the group as well, so "برداشت پول" is recorded
    # as its own rule rather than as the bare "برداشت" inside it.
    DirectionPattern(
        name="debit_blu_bardasht_pool",
        pattern=r"برداشت\s*پول",
        direction=EXPENSE,
        kind="keyword",
    ),
    DirectionPattern(
        name="credit_blu_variz_pool",
        pattern=r"واریز\s*پول",
        direction=INCOME,
        kind="keyword",
    ),
    DirectionPattern(name="debit_bardasht", pattern=r"برداشت", direction=EXPENSE, kind="keyword"),
    DirectionPattern(name="debit_kharid", pattern=r"خرید", direction=EXPENSE, kind="keyword"),
    DirectionPattern(name="debit_pardakht", pattern=r"پرداخت", direction=EXPENSE, kind="keyword"),
    # "کسر" bare: a cut-off sentence still says which way the money went.
    DirectionPattern(name="debit_kasr", pattern=r"کسر", direction=EXPENSE, kind="keyword"),
    DirectionPattern(name="credit_variz", pattern=r"واریز", direction=INCOME, kind="keyword"),
    DirectionPattern(
        name="credit_daryaft",
        pattern=r"دریافت\s*(?:وجه|کننده)?",
        direction=INCOME,
        kind="keyword",
    ),
    # English templates (Saman's English notices, corporate messages). Kept in
    # the keyword group — never before the Persian sentence rules.
    DirectionPattern(
        name="debit_en_withdraw",
        pattern=r"\bwithdraw(?:al|n)?\b",
        direction=EXPENSE,
        kind="keyword",
    ),
    DirectionPattern(
        name="debit_en_purchase_pos",
        pattern=r"\b(?:purchase|pos)\b",
        direction=EXPENSE,
        kind="keyword",
    ),
    DirectionPattern(
        name="debit_en_payment",
        pattern=r"\bpayment\b",
        direction=EXPENSE,
        kind="keyword",
    ),
    DirectionPattern(
        name="debit_en_transfer_from",
        pattern=r"\btransfer\s*(?:from|sent)\b",
        direction=EXPENSE,
        kind="keyword",
    ),
    DirectionPattern(
        name="credit_en_deposit",
        pattern=r"\bdeposit(?:ed)?\b",
        direction=INCOME,
        kind="keyword",
    ),
    DirectionPattern(
        name="credit_en_received",
        pattern=r"\b(?:received|salary)\b",
        direction=INCOME,
        kind="keyword",
    ),
    DirectionPattern(name="credit_credit_en", pattern=r"\bcredit\b", direction=INCOME, kind="keyword"),
    DirectionPattern(name="debit_debit_en", pattern=r"\bdebit\b", direction=EXPENSE, kind="keyword"),
)


# The assembled table. Sentence patterns first (both directions), then tags,
# then keywords — the ordering the module docstring promises, expressed as
# concatenation so it cannot drift from the source order of the groups.
DIRECTION_PATTERNS: tuple[DirectionPattern, ...] = (
    _EXPENSE_SENTENCE_PATTERNS + _CREDIT_SENTENCE_PATTERNS + _TAG_PATTERNS + _KEYWORD_PATTERNS
)


# --------------------------------------------------------------------------
# Balance labels
# --------------------------------------------------------------------------
# Every required spelling maps to the single field `balance_after`:
#
#     موجودی / موجودي
#     موجودی حساب / موجودي فعلي / موجودی فعلی
#     مانده / مانده حساب / مانده قابل برداشت
#
# The Arabic-yeh spellings (``موجودي``, ``موجودي فعلي``) are *not* listed
# separately: `normalize_text` folds U+064A onto the Persian yeh before any
# matching happens, so one spelling covers both. A typography test pins that
# down, so the folding cannot be removed without the duplication becoming
# visible as a failure rather than as a silently narrower table.
#
# Longest form first, so the matched span covers the whole label. That matters
# for proximity: with "مانده حساب: 12,345" matching only "مانده", the figure
# would be hunted from the wrong offset.
BALANCE_LABEL_PATTERNS: tuple[str, ...] = (
    r"مانده\s*قابل\s*برداشت",
    r"موجودی\s*قابل\s*برداشت",
    r"مانده\s*حساب",
    r"موجودی\s*حساب",
    r"موجودی\s*فعلی",
    r"مانده\s*کارت",
    r"موجودی\s*کارت",
    r"مانده\s*سپرده",
    r"موجودی\s*سپرده",
    r"باقی\s*مانده\s*حساب",
    r"باقی\s*مانده",
    r"باقیمانده\s*حساب",
    r"باقیمانده",
    r"اعلام\s*موجودی",
    r"available\s*balance",
    r"remaining\s*balance",
    r"\bbalance\b",
    r"مانده",
    r"موجودی",
)


# Labels that introduce the transaction amount itself.
AMOUNT_LABEL_PATTERNS: tuple[str, ...] = (
    r"مبلغ\s*برداشت",
    r"مبلغ\s*واریز",
    r"مبلغ\s*خرید",
    r"مبلغ\s*پرداخت",
    r"مبلغ\s*انتقال",
    r"مبلغ\s*تراکنش",
    r"مبلغ\s*فاکتور",
    r"مبلغ\s*قابل\s*پرداخت",
    r"مبلغ\s*کسر\s*شده",
    r"به\s*مبلغ",
    r"مبلغ\s*تراکنش",
    r"مبلغ",
    r"وجه\s*تراکنش",
    r"\btransaction\s*amount\b",
    r"\bwithdrawal\s*amount\b",
    r"\bamount\b",
)


# Where a description or merchant name can be read from, when a template carries
# one. The capture runs to the end of the line and is trimmed of any trailing
# balance label.
DESCRIPTION_LABEL_PATTERNS: tuple[str, ...] = (
    r"نام\s*پذیرنده",
    r"نام\s*فروشگاه",
    r"پذیرنده",
    r"فروشگاه",
    r"پایانه",
    r"شماره\s*پایانه",
    r"ترمینال",
    r"شرح\s*تراکنش",
    r"شرح",
    r"توضیحات",
    r"علت",
    r"در\s*وجه",
    r"به\s*نام",
    r"به\s*حساب",
    r"از\s*طرف",
    r"واریز\s*کننده",
    r"انتقال\s*دهنده",
    r"دریافت\s*کننده",
    r"بابت",
    r"\bmerchant\b",
    r"\bterminal\b",
)


# Card numbers, in the forms the templates use. The masked form ("****7284") is
# the card's last four digits and is the more useful of the two; the unmasked
# "کارت 6104" form prints the *first* four, so it is only used when nothing is
# masked, and the order of this tuple encodes that preference.
CARD_PATTERNS: tuple[str, ...] = (
    r"\*{2,}\s*(\d{4})",
    r"کارت\s*(?:مبدا|مقصد)?[\s:*]*\*{2,}\s*(\d{4})",
    r"(?:ending|ending in|ends?\s*(?:in|with)?)\s*(\d{4})",
    r"کارت[\s:*]*(\d{4})",
    r"شماره\s*کارت\s*(?:مبدا|مقصد)?[\s:*]*(\d{4})",
)


# --------------------------------------------------------------------------
# Noise
# --------------------------------------------------------------------------
# Messages that mention money but are not transactions. Each entry is a real
# template category: one-time-password messages quote figures, and bank
# advertising quotes offers and prizes constantly. Importing either as a
# transaction is worse than importing nothing, because the user has to find and
# delete it.
NON_TRANSACTION_PATTERNS: tuple[tuple[str, str], ...] = (
    ("otp", r"رمز\s*(?:یکبار|یک\s*بار)\s*مصرف"),
    ("otp", r"رمز\s*(?:داینامیک|پویا)"),
    ("otp", r"رمز\s*(?:دوم|اول)"),
    ("otp", r"کد\s*(?:تایید|تأیید|ورود|احراز|فعال\s*سازی)"),
    ("otp", r"\botp\b"),
    ("otp", r"کد\s*تنها\s*بار\s*مصرف"),
    # A bare "تخفیف" once rejected any message containing the word — including a
    # real purchase that *mentions* a discount ("۱۰٪ تخفیف خرید ... مبلغ ...
    # کسر شد"). Only advertising-shaped discount wording is noise now.
    ("advertisement", r"تخفیف\s*(?:ویژه|استثنائی|استثنایی|شگفت\s*انگیز|تا\s*\d)"),
    ("advertisement", r"\d+\s*٪\s*تخفیف\s*(?:ویژه|برای|جهت)"),
    ("advertisement", r"قرعه\s*کشی"),
    ("advertisement", r"جشنواره"),
    ("advertisement", r"باشگاه\s*مشتریان"),
    ("advertisement", r"پیشنهاد\s*(?:ویژه|سود)"),
    ("advertisement", r"وام\s*بدون\s*ضامن"),
    ("advertisement", r"طرح\s*(?:فروش|پیش\s*فروش)"),
    # Failed operations quote figures but moved no money: "موجودی کافی نیست"
    # prints the balance without any withdrawal.
    ("failed", r"تراکنش\s*ناموفق"),
    ("failed", r"عملیات\s*ناموفق"),
    ("failed", r"موجودی\s*کافی\s*نیست"),
    ("failed", r"پرداخت\s*ناموفق"),
    ("failed", r"\bfailed\b"),
    ("failed", r"transaction\s*failed"),
    # Reminders and bills-to-pay mention amounts but are requests, not receipts.
    # "قسط" alone is *not* noise: a loan-instalment debit ("پرداخت قسط ... کسر
    # شد") is a real expense. Only reminder-shaped wording is rejected.
    ("request", r"درخواست\s*پرداخت"),
    ("request", r"در\s*انتظار\s*تایید"),
    ("request", r"یادآوری.*قسط|قسط.*یادآوری"),
    ("request", r"سررسید\s*قسط"),
    ("request", r"مهلت\s*پرداخت"),
    ("request", r"صورت\s*حساب\s*صادر\s*شد"),
)


# --------------------------------------------------------------------------
# Date and time
# --------------------------------------------------------------------------
# Jalali dates as banks print them: separator / . or -, year a 13xx/14xx value.
# Latin and Persian digits are already equivalent by the time these run, since
# the text is normalized first.
JALALI_DATE_PATTERN = r"(?<!\d)(1[34]\d{2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{1,2})(?!\d)"
# Gregorian dates, which the few English templates use.
GREGORIAN_DATE_PATTERN = r"(?<!\d)(20\d{2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{1,2})(?!\d)"
# "1405/03/22-11:49" — the compact footer some templates append.
CLOCK_PATTERN = r"(?<!\d)(\d{1,2})\s*:\s*(\d{2})(?!\d)"


# --------------------------------------------------------------------------
# Compiled lookups
# --------------------------------------------------------------------------
# Built once at import time so the parse path is a table walk rather than a
# stream of `re.compile` calls, and so a malformed pattern fails loudly at
# startup instead of at the first message that needs it.
DIRECTION_COMPILED: tuple[tuple[str, re.Pattern[str], str, str], ...] = tuple(
    (rule.name, rule.compile(), rule.direction, rule.kind) for rule in DIRECTION_PATTERNS
)

BALANCE_COMPILED: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (pattern, re.compile(pattern, re.IGNORECASE)) for pattern in BALANCE_LABEL_PATTERNS
)

AMOUNT_LABEL_COMPILED: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (pattern, re.compile(pattern, re.IGNORECASE)) for pattern in AMOUNT_LABEL_PATTERNS
)

DESCRIPTION_COMPILED: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (pattern, re.compile(pattern, re.IGNORECASE)) for pattern in DESCRIPTION_LABEL_PATTERNS
)

NON_TRANSACTION_COMPILED: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(pattern, re.IGNORECASE)) for name, pattern in NON_TRANSACTION_PATTERNS
)

CARD_COMPILED: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE) for pattern in CARD_PATTERNS
)


# The unit words, for the "which unit did this message use" report and for the
# warning shown when a message named none at all.
UNIT_WORDS: tuple[tuple[str, str], ...] = (
    ("ریال", RIAL),
    ("تومان", TOMAN),
    ("تومن", TOMAN),
)


