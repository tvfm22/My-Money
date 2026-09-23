"""Tests for normalize_text / fingerprint — the matching surface every pattern uses."""

from django.test import SimpleTestCase

from apps.sms.normalize import ZWNJ, fingerprint, fold_keywords, normalize_text


class NormalizeTextTests(SimpleTestCase):
    def test_empty_text_normalizes_to_empty(self):
        self.assertEqual(normalize_text(""), "")

    def test_persian_and_arabic_indic_digits_become_latin(self):
        self.assertEqual(normalize_text("۴۸۸٬۱۵۲"), "488,152")
        self.assertEqual(normalize_text("٤٨٨"), "488")

    def test_arabic_letter_forms_become_persian(self):
        # Arabic yeh and kaf, as they arrive from phone keyboards.
        raw = "\u0645\u0648\u062c\u0648\u062f\u064a \u0643\u0627\u0631\u062a"
        self.assertEqual(normalize_text(raw), "موجودی کارت")

    def test_persian_separators_become_latin(self):
        raw = "1\u066c500\u066c000\u066b50"
        self.assertEqual(normalize_text(raw), "1,500,000.50")

    def test_unicode_minus_and_nbsp_become_ascii(self):
        self.assertEqual(normalize_text("\u22121\u00a0ریال"), "-1 ریال")

    def test_zwnj_becomes_a_plain_space(self):
        self.assertEqual(normalize_text("می\u200cشود"), "می شود")
        self.assertNotIn(ZWNJ, normalize_text("می\u200cشود"))

    def test_whitespace_runs_collapse_to_single_spaces(self):
        self.assertEqual(normalize_text("مبلغ  \n 500\tریال"), "مبلغ 500 ریال")

    def test_normalization_is_idempotent(self):
        raw = "موجودي: ۴۸۸٬۱۵۲ ریال"
        once = normalize_text(raw)
        self.assertEqual(normalize_text(once), once)


class FingerprintTests(SimpleTestCase):
    def test_same_text_same_fingerprint(self):
        self.assertEqual(fingerprint("مبلغ 500 ریال"), fingerprint("مبلغ 500 ریال"))

    def test_glyph_variants_share_a_fingerprint(self):
        # The same message pasted from two phones differs in digit glyphs and
        # Arabic/Persian letter forms — it must still hash identically or the
        # duplicate guard misses it.
        self.assertEqual(fingerprint("مبلغ ۵۰۰٬۰۰۰ ریال"), fingerprint("مبلغ 500,000 ریال"))

    def test_different_text_different_fingerprint(self):
        self.assertNotEqual(fingerprint("مبلغ 500 ریال"), fingerprint("مبلغ 501 ریال"))

    def test_fingerprint_is_sha256_hex(self):
        fp = fingerprint("مبلغ 500 ریال")
        self.assertEqual(len(fp), 64)
        int(fp, 16)  # must not raise


class FoldKeywordsTests(SimpleTestCase):
    def test_latin_words_lowercase(self):
        self.assertEqual(fold_keywords("TOMAN Pos IRR"), "toman pos irr")