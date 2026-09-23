"""Tests for automatic message reading: the switch, the check, and idempotency.

The property under test throughout this module is one sentence: **running the
check again must not produce a second transaction.** Everything else — the
toggle, the counts, the labels — exists to make that property visible to the
user rather than to replace it.

The tests are grouped the way the failure modes are:

*   *Idempotency* — the same message arriving twice, or the action being pressed
    twice, or the automatic pass running after a manual one.
*   *What counts as new* — non-transactional messages, and two genuinely
    separate purchases that happen to share an amount and a date.
*   *The switch* — on, off, and off-then-on, and the fact that off stops the
    automatic pass while leaving the manual action alone.
*   *Privacy* — the message text is never written to a log.
"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.categories.models import Category, CategoryKind
from apps.sms.models import ItemStatus, SmsImportBatch, SmsImportItem
from apps.transactions.models import Transaction, TransactionType

User = get_user_model()

AUTO_IMPORT_URL = "/api/sms/auto-import/"
SYNC_URL = "/api/sms/auto-import/sync/"

# --- messages ---------------------------------------------------------------
#
# Copied from the parser's own fixtures rather than invented, so a change in
# what the parser accepts shows up here as a failure instead of as a test that
# was quietly written to match the old behaviour.

EXPENSE_SMS = "خرید با کارت ****7284 مبلغ 450,000 ریال\n1405/06/15"
INCOME_SMS = "به حساب شما مبلغ 1,500,000 ریال واریز گردید.\nموجودی: 2,500,000 ریال"

# Same amount, same date, different words: two real purchases, not a repeat.
SAME_AMOUNT_OTHER_WORDING = "خرید از فروشگاه رفاه مبلغ 450,000 ریال\n1405/06/15"

# A bank's marketing message. It carries an amount and is still not a
# transaction.
ADVERTISING_SMS = "جشنواره قرعه کشی بانک سامان با تخفیف ویژه. مبلغ 500,000 ریال"

# A figure that must never appear in a log line.
SECRET_AMOUNT_MARKER = "450,000"


class SmsAutoImportTestCase(TestCase):
    """Shared fixture: one owner, one intruder, and the two categories."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="owner@example.com", password="pw-12345678"
        )
        self.other = User.objects.create_user(
            email="other@example.com", password="pw-12345678"
        )

        self.expense_category = Category.objects.create(
            user=self.user, name="خرید روزمره", kind=CategoryKind.EXPENSE
        )
        self.income_category = Category.objects.create(
            user=self.user, name="حقوق", kind=CategoryKind.INCOME
        )

        self.account = Account.objects.create(
            user=self.user, name="بانک ملت", account_type="bank"
        )

        self.client = APIClient()
        self.client.force_authenticate(self.user)

        self.intruder = APIClient()
        self.intruder.force_authenticate(self.other)

    # -- helpers -------------------------------------------------------------

    def sync(self, *, text="", **extra):
        payload = {"text": text} if text else {}
        payload.update(extra)
        return self.client.post(SYNC_URL, payload, format="json")

    def state(self):
        response = self.client.get(AUTO_IMPORT_URL)
        self.assertEqual(response.status_code, 200)
        return response.data

    def staged_items(self):
        return SmsImportItem.objects.filter(user=self.user)


class SyncIdempotencyTests(SmsAutoImportTestCase):
    """A message is staged once, however many times it is looked at."""

    def test_new_bank_message_is_staged_as_a_transaction(self):
        """Test 1 — SMS → parse → a transaction row exists to review."""
        response = self.sync(text=EXPENSE_SMS)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["summary"]["checked"], 1)
        self.assertEqual(response.data["summary"]["new_transactions"], 1)
        self.assertIsNotNone(response.data["batch_id"])

        (item,) = self.staged_items()
        self.assertEqual(item.direction, TransactionType.EXPENSE)
        self.assertEqual(str(item.amount), "45000.00")
        self.assertTrue(item.is_transaction)
        self.assertEqual(item.status, ItemStatus.PENDING)

    def test_same_message_twice_stages_one_row(self):
        """Test 2 — the identical message does not become a second row."""
        self.sync(text=EXPENSE_SMS)
        response = self.sync(text=EXPENSE_SMS)

        self.assertEqual(self.staged_items().count(), 1)
        self.assertEqual(response.data["summary"]["new_transactions"], 0)
        self.assertEqual(response.data["summary"]["duplicate"], 1)
        self.assertEqual(response.data["summary"]["without_new"], 1)
        # Nothing new means no batch is created at all — an empty batch on the
        # review screen would be a place the user has to go and find nothing.
        self.assertIsNone(response.data["batch_id"])

    def test_repeating_the_action_never_multiplies_rows(self):
        """Test 3 — pressing the button five times leaves one row."""
        for _ in range(5):
            self.sync(text=EXPENSE_SMS)

        self.assertEqual(self.staged_items().count(), 1)

    def test_mixed_blob_reports_three_numbers(self):
        """The summary the screen shows: checked / new / without new."""
        blob = "\n\n".join([EXPENSE_SMS, INCOME_SMS, ADVERTISING_SMS])
        response = self.sync(text=blob)
        summary = response.data["summary"]

        self.assertEqual(summary["checked"], 3)
        self.assertEqual(summary["new_transactions"], 2)
        self.assertEqual(summary["without_new"], 1)
        # The advertising message is stored — the user may want to see it was
        # read and dismissed — but it is never a transaction.
        self.assertEqual(summary["not_transaction"], 1)

    def test_second_pass_over_a_blob_finds_nothing_new(self):
        blob = "\n\n".join([EXPENSE_SMS, INCOME_SMS])
        self.sync(text=blob)
        response = self.sync(text=blob)

        self.assertEqual(response.data["summary"]["new_transactions"], 0)
        self.assertEqual(response.data["summary"]["duplicate"], 2)
        self.assertEqual(self.staged_items().count(), 2)

    def test_a_skipped_message_is_not_offered_again(self):
        """Skip must mean skip, not ask me later."""
        self.sync(text=EXPENSE_SMS)
        (item,) = self.staged_items()
        item.status = ItemStatus.SKIPPED
        item.save(update_fields=["status"])

        response = self.sync(text=EXPENSE_SMS)

        self.assertEqual(self.staged_items().count(), 1)
        self.assertEqual(response.data["summary"]["new_transactions"], 0)

    def test_one_user_does_not_deduplicate_against_another(self):
        """Fingerprints are scoped to their owner, not global."""
        self.sync(text=EXPENSE_SMS)

        intruder_response = self.intruder.post(SYNC_URL, {"text": EXPENSE_SMS}, format="json")

        self.assertEqual(intruder_response.status_code, 200)
        self.assertEqual(intruder_response.data["summary"]["new_transactions"], 1)
        self.assertEqual(SmsImportItem.objects.filter(user=self.other).count(), 1)


class NonTransactionalMessageTests(SmsAutoImportTestCase):
    """Test 4 — a message that is not a transaction creates no transaction."""

    def test_advertising_is_stored_but_is_not_a_transaction(self):
        response = self.sync(text=ADVERTISING_SMS)

        self.assertEqual(response.data["summary"]["new_transactions"], 0)
        (item,) = self.staged_items()
        self.assertFalse(item.is_transaction)

    def test_advertising_alone_creates_no_ledger_row(self):
        self.sync(text=ADVERTISING_SMS)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 0)

    def test_empty_text_records_a_check_without_staging_anything(self):
        response = self.sync()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["summary"]["checked"], 0)
        self.assertIsNone(response.data["batch_id"])
        self.assertEqual(self.staged_items().count(), 0)
        self.assertIsNotNone(self.state()["last_checked_at"])


class SameAmountSameDateTests(SmsAutoImportTestCase):
    """Test 11 — two real purchases are not one duplicate."""

    def test_two_messages_with_the_same_amount_and_date_both_survive(self):
        blob = "\n\n".join([EXPENSE_SMS, SAME_AMOUNT_OTHER_WORDING])
        response = self.sync(text=blob)

        self.assertEqual(response.data["summary"]["new_transactions"], 2)
        items = list(self.staged_items())
        self.assertEqual(len(items), 2)
        # Neither is rejected as a duplicate: identical money on the same day is
        # normal, and deciding otherwise would silently drop a real purchase.
        self.assertEqual([item.status for item in items], [ItemStatus.PENDING] * 2)
        self.assertEqual({str(item.amount) for item in items}, {"45000.00"})

    def test_the_second_one_carries_a_soft_warning_not_a_rejection(self):
        """Once one is imported, the other is *questioned*, not dropped."""
        self.sync(text=EXPENSE_SMS)
        (first,) = self.staged_items()
        first.category = self.expense_category
        first.status = ItemStatus.IMPORTED
        first.save(update_fields=["category", "status"])

        self.sync(text=SAME_AMOUNT_OTHER_WORDING)

        second = self.staged_items().exclude(pk=first.pk).get()
        self.assertEqual(second.status, ItemStatus.PENDING)
        self.assertTrue(second.warnings, "the possible-duplicate warning is missing")


class AutoImportSwitchTests(SmsAutoImportTestCase):
    """Test 5, 6, 7 — the switch, its two states, and turning it back on."""

    def test_the_switch_starts_off(self):
        state = self.state()

        self.assertFalse(state["enabled"])
        self.assertIsNone(state["last_checked_at"])
        self.assertEqual(state["imported_from_sms_count"], 0)

    def test_turning_it_on_is_reported_back(self):
        response = self.client.patch(AUTO_IMPORT_URL, {"enabled": True}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["enabled"])
        self.assertTrue(self.state()["enabled"])

    def test_turning_it_on_twice_is_harmless(self):
        self.client.patch(AUTO_IMPORT_URL, {"enabled": True}, format="json")
        response = self.client.patch(AUTO_IMPORT_URL, {"enabled": True}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["enabled"])

    def test_it_can_be_turned_off_and_on_again(self):
        """Test 6 — the switch is not one-way."""
        self.client.patch(AUTO_IMPORT_URL, {"enabled": True}, format="json")
        self.client.patch(AUTO_IMPORT_URL, {"enabled": False}, format="json")
        self.assertFalse(self.state()["enabled"])

        response = self.client.patch(AUTO_IMPORT_URL, {"enabled": True}, format="json")
        self.assertTrue(response.data["enabled"])

    def test_an_empty_toggle_body_is_rejected(self):
        """Saying nothing is not the same request as saying "on"."""
        response = self.client.patch(AUTO_IMPORT_URL, {}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.state()["enabled"])

    def test_the_manual_check_works_while_the_switch_is_off(self):
        """Test 7 — off stops the automatic pass, not the user's own action."""
        self.assertFalse(self.state()["enabled"])

        response = self.sync(text=EXPENSE_SMS)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["summary"]["new_transactions"], 1)

    def test_the_state_endpoint_is_scoped_to_its_owner(self):
        self.client.patch(AUTO_IMPORT_URL, {"enabled": True}, format="json")

        self.assertFalse(self.intruder.get(AUTO_IMPORT_URL).data["enabled"])


class AutoImportStateTests(SmsAutoImportTestCase):
    """What the screen reads: the counts, the label, and the sentence."""

    def test_the_last_check_time_is_recorded_and_labelled(self):
        self.sync(text=EXPENSE_SMS)
        state = self.state()

        self.assertIsNotNone(state["last_checked_at"])
        self.assertIsNotNone(state["last_checked_label"])
        # A Jalali label, not an ISO string — the screen never formats a date.
        self.assertIn("1405", state["last_checked_label"])

    def test_pending_transactions_are_counted_until_they_are_imported(self):
        self.sync(text=EXPENSE_SMS)
        self.assertEqual(self.state()["pending_count"], 1)

        (item,) = self.staged_items()
        item.category = self.expense_category
        item.save(update_fields=["category"])

        self.client.post(
            f"/api/sms/batches/{item.batch_id}/commit/", {}, format="json"
        )

        state = self.state()
        self.assertEqual(state["pending_count"], 0)
        self.assertEqual(state["imported_from_sms_count"], 1)

    def test_a_transaction_from_a_message_reports_its_source(self):
        self.sync(text=EXPENSE_SMS)
        (item,) = self.staged_items()
        item.category = self.expense_category
        item.save(update_fields=["category"])
        self.client.post(f"/api/sms/batches/{item.batch_id}/commit/", {}, format="json")

        (transaction,) = Transaction.objects.filter(user=self.user)
        response = self.client.get(f"/api/transactions/{transaction.pk}/")

        self.assertEqual(response.data["source"], "sms")
        self.assertEqual(response.data["source_label"], "از پیامک")

    def test_a_hand_entered_transaction_is_not_labelled_as_sms(self):
        self.client.post(
            "/api/transactions/",
            {
                "transaction_type": TransactionType.EXPENSE,
                "amount": "120000",
                "category": self.expense_category.id,
                "account": self.account.id,
                "occurred_on": "2026-09-06",
            },
            format="json",
        )

        (transaction,) = Transaction.objects.filter(user=self.user)
        response = self.client.get(f"/api/transactions/{transaction.pk}/")

        self.assertEqual(response.data["source"], "manual")
        self.assertEqual(response.data["source_label"], "دستی")

    def test_deleting_the_transaction_drops_the_count_again(self):
        """The count follows the ledger instead of drifting away from it."""
        self.sync(text=EXPENSE_SMS)
        (item,) = self.staged_items()
        item.category = self.expense_category
        item.save(update_fields=["category"])
        self.client.post(f"/api/sms/batches/{item.batch_id}/commit/", {}, format="json")
        self.assertEqual(self.state()["imported_from_sms_count"], 1)

        Transaction.objects.filter(user=self.user).delete()

        self.assertEqual(self.state()["imported_from_sms_count"], 0)


class PrivacyTests(SmsAutoImportTestCase):
    """Test 14 — nothing sensitive reaches a log, and only the last four digits
    are kept as a field."""

    def test_the_message_body_is_never_logged(self):
        records: list[str] = []

        class Collector(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record.getMessage())

        root = logging.getLogger()
        collector = Collector()
        previous_level = root.level
        root.addHandler(collector)
        root.setLevel(logging.DEBUG)
        try:
            self.sync(text=EXPENSE_SMS)
        finally:
            root.removeHandler(collector)
            root.setLevel(previous_level)

        leaked = [line for line in records if SECRET_AMOUNT_MARKER in line]
        self.assertEqual(leaked, [], f"the message body reached a log line: {leaked}")

    def test_the_check_response_does_not_echo_message_bodies(self):
        """The counts travel; the text stays where it was stored."""
        response = self.sync(text=EXPENSE_SMS)

        body = str(response.data)
        self.assertNotIn("کارت", body)
        self.assertNotIn(SECRET_AMOUNT_MARKER, body)

    def test_only_the_last_four_card_digits_become_a_field(self):
        self.sync(text="خرید با کارت ****7284 مبلغ 450,000 ریال")

        (item,) = self.staged_items()
        self.assertEqual(item.card_last4, "7284")

    def test_an_unmasked_card_number_never_reaches_a_structured_field(self):
        """The full number may sit in `raw_text` — the review screen shows the
        bank's own words — but it must not be copied into any field the app
        searches, groups or displays as data."""
        self.sync(text="خرید با کارت 6104-3378-1234-7284 مبلغ 450,000 ریال")

        (item,) = self.staged_items()
        for value in (item.card_last4, item.merchant, item.description, item.bank_label):
            self.assertNotIn("6104337812347284", value.replace("-", ""))
        self.assertLessEqual(len(item.card_last4), 4)
