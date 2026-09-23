"""Tests for the SMS import services: splitting, staging, committing."""

import datetime as dt
from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import Account
from apps.categories.models import Category, CategoryKind
from apps.sms.models import BatchStatus, ItemStatus
from apps.sms.services import (
    ALREADY_IMPORTED_WARNING,
    OUT_OF_PERIOD_WARNING,
    POSSIBLE_DUPLICATE_WARNING,
    apply_balance_reconciliation,
    balance_reconciliation,
    bulk_update_items,
    commit_batch,
    create_batch,
    dismiss_reminder,
    previous_period,
    reminder_state,
    split_messages,
)
from apps.transactions.models import Transaction
from apps.users.models import User

EXPENSE_MSG = "1405/06/15 مبلغ 200,000 ریال کسر گردید"
INCOME_MSG = "1405/06/16 مبلغ 1,500,000 ریال به حساب شما واریز شد"
NO_DATE_MSG = "مبلغ 100,000 ریال کسر گردید"
OTP_MSG = "کد تایید بانک: 123456. این کد را به هیچکس ندهید."
BALANCE_MSG = "1405/06/15 مبلغ 200,000 ریال کسر گردید. مانده 1,000,000 ریال"


class SmsServiceTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="sara@example.com", password="test123")
        cls.other = User.objects.create_user(email="other@example.com", password="test123")
        cls.expense_category = Category.objects.create(
            user=cls.user, name="خوراک", kind=CategoryKind.EXPENSE
        )
        cls.income_category = Category.objects.create(
            user=cls.user, name="حقوق", kind=CategoryKind.INCOME
        )
        cls.account = Account.objects.create(user=cls.user, name="بانک ملت")


class SplitMessagesTests(SmsServiceTestBase):
    def test_blank_lines_separate_messages(self):
        messages = split_messages(f"{EXPENSE_MSG}\n\n{OTP_MSG}")
        self.assertEqual(messages, [("", EXPENSE_MSG), ("", OTP_MSG)])

    def test_separator_lines_split_messages(self):
        raw = f"{EXPENSE_MSG}\n---\n{INCOME_MSG}\n===\n{OTP_MSG}"
        messages = split_messages(raw)
        self.assertEqual(len(messages), 3)

    def test_explicit_sender_line(self):
        messages = split_messages(f"از: بانک ملت\n{INCOME_MSG}")
        self.assertEqual(messages, [("بانک ملت", INCOME_MSG)])

    def test_bare_sender_number_line(self):
        raw = "20004861\n-1,100,000\nمانده 17,712,600"
        sender, body = split_messages(raw)[0]
        self.assertEqual(sender, "20004861")
        self.assertIn("مانده", body)

    def test_persian_first_line_is_not_a_sender(self):
        raw = f"{INCOME_MSG}\nسطر دوم"
        sender, body = split_messages(raw)[0]
        self.assertEqual(sender, "")
        self.assertIn("سطر دوم", body)

    def test_no_separators_means_one_message(self):
        messages = split_messages(f"{EXPENSE_MSG}\n{INCOME_MSG}")
        self.assertEqual(len(messages), 1)

    def test_empty_paste_yields_no_messages(self):
        self.assertEqual(split_messages(""), [])
        self.assertEqual(split_messages("   \n  "), [])

    def test_previous_period_is_the_month_that_ended(self):
        self.assertEqual(previous_period(dt.date(2026, 9, 23)), (1405, 6))
        # The wrap-around: on 1405/01/01 the question is "did اسفند 1404 get in?"
        self.assertEqual(previous_period(dt.date(2026, 3, 21)), (1404, 12))


class CreateBatchTests(SmsServiceTestBase):
    def test_items_are_staged_with_parsed_fields(self):
        batch = create_batch(
            self.user,
            raw_text=f"{EXPENSE_MSG}\n\n{OTP_MSG}",
            period_year=1405,
            period_month=6,
        )
        self.assertEqual(batch.items.count(), 2)
        self.assertEqual(batch.status, BatchStatus.DRAFT)

        expense = batch.items.get(raw_text=EXPENSE_MSG)
        self.assertTrue(expense.is_transaction)
        self.assertEqual(expense.status, ItemStatus.PENDING)
        self.assertEqual(expense.direction, "expense")
        self.assertEqual(expense.amount, Decimal("20000.00"))
        self.assertEqual(expense.occurred_on, dt.date(2026, 9, 6))
        self.assertEqual(expense.date_source, "jalali")
        self.assertEqual(expense.account, batch.account)

        noise = batch.items.get(noise_kind="otp")
        self.assertFalse(noise.is_transaction)
        self.assertIsNone(noise.amount)

    def test_period_defaults_to_the_month_that_ended(self):
        batch = create_batch(self.user, raw_text=EXPENSE_MSG)
        expected_year, expected_month = previous_period()
        self.assertEqual((batch.period_year, batch.period_month), (expected_year, expected_month))

    def test_account_is_propagated_to_items(self):
        batch = create_batch(self.user, raw_text=EXPENSE_MSG, account=self.account)
        self.assertEqual(batch.account, self.account)
        self.assertEqual(batch.items.get().account, self.account)

    def test_category_is_suggested_from_the_message(self):
        batch = create_batch(
            self.user,
            raw_text="1405/06/16 خرید از رستوران 150,000 ریال",
            period_year=1405,
            period_month=6,
        )
        item = batch.items.get()
        self.assertEqual(item.category, self.expense_category)

    def test_out_of_period_date_is_flagged(self):
        raw = "1405/07/01 مبلغ 200,000 ریال کسر گردید"
        batch = create_batch(self.user, raw_text=raw, period_year=1405, period_month=6)
        self.assertIn(OUT_OF_PERIOD_WARNING, batch.items.get().warnings)


class DuplicateTests(SmsServiceTestBase):
    def test_same_message_twice_in_one_paste(self):
        batch = create_batch(
            self.user, raw_text=f"{EXPENSE_MSG}\n\n{EXPENSE_MSG}",
            period_year=1405, period_month=6,
        )
        # A message cannot appear twice in one reading session: the second
        # copy is simply not staged (unique_fingerprint_per_batch).
        self.assertEqual(batch.items.count(), 1)
        self.assertEqual(batch.items.get().status, ItemStatus.PENDING)

    def test_reimporting_the_same_message_is_flagged(self):
        create_batch(self.user, raw_text=EXPENSE_MSG, period_year=1405, period_month=6)
        second = create_batch(
            self.user, raw_text=EXPENSE_MSG, period_year=1405, period_month=6
        )
        item = second.items.get()
        self.assertEqual(item.status, ItemStatus.DUPLICATE)
        self.assertIn(ALREADY_IMPORTED_WARNING, item.warnings)

    def test_skipped_message_may_be_imported_again(self):
        first = create_batch(self.user, raw_text=EXPENSE_MSG, period_year=1405, period_month=6)
        item = first.items.get()
        item.status = ItemStatus.SKIPPED
        item.save(update_fields=["status"])

        second = create_batch(self.user, raw_text=EXPENSE_MSG, period_year=1405, period_month=6)
        fresh = second.items.get()
        self.assertEqual(fresh.status, ItemStatus.PENDING)
        self.assertNotIn(ALREADY_IMPORTED_WARNING, fresh.warnings)

    def test_same_amount_and_date_elsewhere_warns_softly(self):
        first = create_batch(
            self.user, raw_text=EXPENSE_MSG, period_year=1405, period_month=6
        )
        item = first.items.get(raw_text=EXPENSE_MSG)
        item.category = self.expense_category
        item.save(update_fields=["category"])
        commit_batch(self.user, first)

        # Same money, different words: not a fingerprint duplicate, but a
        # likely duplicate the user should glance at.
        other_words = "1405/06/15 خرید 200,000 ریال از فروشگاه"
        second = create_batch(
            self.user, raw_text=other_words, period_year=1405, period_month=6
        )
        fresh = second.items.get()
        self.assertEqual(fresh.status, ItemStatus.PENDING)
        self.assertIn(POSSIBLE_DUPLICATE_WARNING, fresh.warnings)


class CommitBatchTests(SmsServiceTestBase):
    def _staged_batch(self, raw_text, **kwargs):
        batch = create_batch(
            self.user, raw_text=raw_text, period_year=1405, period_month=6, **kwargs
        )
        for item in batch.items.all():
            if item.direction == "income":
                item.category = self.income_category
            elif item.direction == "expense":
                item.category = self.expense_category
            if item.category_id:
                item.save(update_fields=["category"])
        return batch

    def test_commit_writes_transactions_and_marks_items(self):
        raw = f"{EXPENSE_MSG}\n\n{INCOME_MSG}\n\n{OTP_MSG}"
        batch = self._staged_batch(raw, account=self.account)

        result = commit_batch(self.user, batch)

        self.assertEqual(result["imported_count"], 2)
        self.assertEqual(result["not_transaction_count"], 1)
        self.assertEqual(result["missing_category_count"], 0)
        self.assertEqual(result["incomplete_count"], 0)

        expense_tx = Transaction.objects.get(amount=Decimal("20000.00"))
        self.assertEqual(expense_tx.transaction_type, "expense")
        self.assertEqual(expense_tx.account, self.account)
        self.assertEqual(expense_tx.category, self.expense_category)

        income_tx = Transaction.objects.get(amount=Decimal("150000.00"))
        self.assertEqual(income_tx.transaction_type, "income")

        expense_item = batch.items.get(raw_text=EXPENSE_MSG)
        self.assertEqual(expense_item.status, ItemStatus.IMPORTED)
        self.assertEqual(expense_item.transaction, expense_tx)
        self.assertEqual(batch.status, BatchStatus.COMMITTED)

        noise_item = batch.items.get(noise_kind="otp")
        self.assertEqual(noise_item.status, ItemStatus.PENDING)

    def test_committing_only_selected_items(self):
        raw = f"{EXPENSE_MSG}\n\n{INCOME_MSG}"
        batch = self._staged_batch(raw, account=self.account)
        ids = list(batch.items.values_list("id", flat=True))

        result = commit_batch(self.user, batch, item_ids=ids[:1])
        self.assertEqual(result["imported_count"], 1)
        self.assertEqual(batch.items.filter(status=ItemStatus.IMPORTED).count(), 1)
        self.assertEqual(batch.items.filter(status=ItemStatus.PENDING).count(), 1)

    def test_message_without_date_is_committed_on_the_period_start(self):
        batch = self._staged_batch(NO_DATE_MSG, account=self.account)
        commit_batch(self.user, batch)

        item = batch.items.get()
        self.assertEqual(item.occurred_on, dt.date(2026, 8, 23))  # 1405/06/01
        self.assertEqual(item.date_source, "assumed")
        self.assertEqual(Transaction.objects.get().occurred_on, dt.date(2026, 8, 23))

    def test_committing_someone_elses_batch_is_rejected(self):
        batch = create_batch(
            self.other, raw_text=EXPENSE_MSG, period_year=1405, period_month=6
        )
        with self.assertRaises(ValueError):
            commit_batch(self.user, batch)


class BalanceReconciliationTests(SmsServiceTestBase):
    def test_without_an_account_there_is_nothing_to_reconcile(self):
        batch = create_batch(self.user, raw_text=BALANCE_MSG, period_year=1405, period_month=6)
        result = balance_reconciliation(self.user, batch)
        self.assertFalse(result["available"])
        self.assertIn("حساب", result["message"])

    def test_without_a_balance_reading_it_is_unavailable(self):
        batch = create_batch(
            self.user, raw_text=EXPENSE_MSG, period_year=1405, period_month=6,
            account=self.account,
        )
        result = balance_reconciliation(self.user, batch)
        self.assertFalse(result["available"])

    def test_implied_opening_and_drift(self):
        batch = create_batch(
            self.user, raw_text=BALANCE_MSG, period_year=1405, period_month=6,
            account=self.account,
        )
        # A transaction the ledger has, dated after the SMS reading.
        Transaction.objects.create(
            user=self.user,
            transaction_type="expense",
            amount=Decimal("50000.00"),
            category=self.expense_category,
            account=self.account,
            occurred_on=dt.date(2026, 9, 10),
        )

        result = balance_reconciliation(self.user, batch)
        self.assertTrue(result["available"])
        self.assertEqual(result["reading_amount"], Decimal("100000.00"))
        self.assertEqual(result["later_income"], Decimal("0.00"))
        self.assertEqual(result["later_expense"], Decimal("50000.00"))
        # reading + later expense  ->  what the opening must have been
        self.assertEqual(result["implied_opening_balance"], Decimal("150000.00"))
        self.assertEqual(result["drift"], Decimal("150000.00"))
        self.assertFalse(result["matches"])

    def test_apply_sets_the_opening_balance(self):
        batch = create_batch(
            self.user, raw_text=BALANCE_MSG, period_year=1405, period_month=6,
            account=self.account,
        )
        result = apply_balance_reconciliation(self.user, batch)
        self.assertTrue(result["applied"])
        self.account.refresh_from_db()
        # No transactions after the reading, so the opening is the reading.
        self.assertEqual(self.account.opening_balance, Decimal("100000.00"))

        # Second call agrees with the ledger: drift zero, nothing to fix.
        again = balance_reconciliation(self.user, batch)
        self.assertTrue(again["matches"])
        self.assertEqual(again["drift"], Decimal("0.00"))


class BulkUpdateTests(SmsServiceTestBase):
    def _two_items(self):
        batch = create_batch(
            self.user,
            raw_text=f"{EXPENSE_MSG}\n\n{INCOME_MSG}",
            period_year=1405,
            period_month=6,
        )
        return list(batch.items.all())

    def test_category_only_lands_on_matching_directions(self):
        items = self._two_items()
        result = bulk_update_items(self.user, items, category=self.expense_category)
        self.assertEqual(result["updated_count"], 1)
        self.assertEqual(result["skipped_count"], 1)
        expense = next(item for item in items if item.direction == "expense")
        income = next(item for item in items if item.direction == "income")
        self.assertEqual(expense.category, self.expense_category)
        self.assertIsNone(income.category)

    def test_other_users_items_are_skipped(self):
        batch = create_batch(
            self.other, raw_text=EXPENSE_MSG, period_year=1405, period_month=6
        )
        result = bulk_update_items(
            self.user, list(batch.items.all()), category=self.expense_category
        )
        self.assertEqual(result, {"updated_count": 0, "skipped_count": 1})

    def test_unknown_fields_are_not_applied(self):
        (item,) = list(
            create_batch(
                self.user, raw_text=EXPENSE_MSG, period_year=1405, period_month=6
            ).items.all()
        )
        bulk_update_items(self.user, [item], noise_kind="otp")
        item.refresh_from_db()
        self.assertEqual(item.noise_kind, "")

    def test_spending_type_is_never_set_on_income(self):
        (income,) = list(
            create_batch(
                self.user, raw_text=INCOME_MSG, period_year=1405, period_month=6
            ).items.all()
        )
        bulk_update_items(self.user, [income], spending_type="essential")
        income.refresh_from_db()
        self.assertEqual(income.spending_type, "")


class ReminderTests(SmsServiceTestBase):
    def test_fresh_user_is_reminded(self):
        state = reminder_state(self.user, today=dt.date(2026, 9, 23))  # 1405/07/02
        self.assertTrue(state["should_remind"])
        self.assertTrue(state["within_window"])
        self.assertFalse(state["has_batch"])
        self.assertIn("پیامک‌های بانکی آن را وارد کنید", state["message"])

    def test_committed_batch_stops_the_reminder(self):
        batch = create_batch(
            self.user, raw_text=EXPENSE_MSG, period_year=1405, period_month=6
        )
        item = batch.items.get()
        item.category = self.expense_category
        item.save(update_fields=["category"])
        commit_batch(self.user, batch)

        state = reminder_state(self.user, today=dt.date(2026, 9, 23))
        self.assertTrue(state["has_committed_batch"])
        self.assertFalse(state["should_remind"])
        self.assertEqual(state["message"], "پیامک‌های ماه گذشته ثبت شده است.")

    def test_pending_items_change_the_message(self):
        create_batch(self.user, raw_text=EXPENSE_MSG, period_year=1405, period_month=6)
        state = reminder_state(self.user, today=dt.date(2026, 9, 23))
        self.assertTrue(state["should_remind"])
        self.assertEqual(state["suggested_month"], 6)
        self.assertIn("بررسی‌نشده", state["message"])

    def test_dismissal_hides_the_reminder_for_that_period(self):
        dismiss_reminder(self.user, 1405, 6)
        # Idempotent.
        dismiss_reminder(self.user, 1405, 6)
        state = reminder_state(self.user, today=dt.date(2026, 9, 23))
        self.assertTrue(state["dismissed"])
        self.assertFalse(state["should_remind"])

    def test_after_the_window_the_reminder_goes_away(self):
        state = reminder_state(self.user, today=dt.date(2026, 10, 15))  # 1405/07/23
        self.assertFalse(state["within_window"])
        self.assertFalse(state["should_remind"])