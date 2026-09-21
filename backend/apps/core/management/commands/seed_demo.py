"""Seed realistic Persian demo data.

Creates a demo account with several months of plausible Iranian household
finance: salary income, groceries, transport, rent, utilities, a couple of
debts, and a small asset portfolio.

Design notes
------------
*   Deterministic: seeded with a fixed random seed, so repeated runs produce the
    same data and screenshots stay stable.
*   Relative to today: spending is generated for the current Jalali month and
    the previous five, so the dashboard always has meaningful data regardless of
    when it is run.
*   Plausible magnitudes: amounts are in Toman and scaled to a middle-income
    Tehran household. Rent is the largest line, groceries sit around 8-12
    million a month, a taxi ride is a few hundred thousand.
*   Idempotent: wipes the demo user's data first, so it can be re-run safely.

Usage:
    python manage.py seed_demo
    python manage.py seed_demo --email me@example.com --password mypassword
"""

from __future__ import annotations

import datetime as dt
import random
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Account, AccountType
from apps.assets.models import Asset, AssetType, AssetValuation
from apps.budgets.models import Budget, BudgetItem
from apps.categories.models import Category, CategoryKind
from apps.categories.services import seed_default_categories
from apps.core.jalali import add_jalali_months, current_jalali_month, jalali_month_bounds, to_gregorian
from apps.debts.models import Debt, DebtDirection, DebtPayment
from apps.transactions.models import Tag, Transaction, TransactionType

User = get_user_model()

SEED = 20260920

# A household's monthly pattern. Each entry is
# (category name, count_min, count_max, amount_min, amount_max, description pool)
#
# The amount ranges are tuned so that a typical month lands at roughly 85-95% of
# the corresponding budget below. That produces a demo where most categories are
# comfortably inside budget, a couple are near the limit, and one or two tip
# over — which is what a real month looks like, and which exercises every status
# on the ladder rather than showing a uniformly alarming dashboard.
EXPENSE_PATTERN: list[tuple[str, int, int, int, int, list[str]]] = [
    ("خوراک", 5, 9, 300_000, 1_100_000, ["خرید هفتگی", "میوه و سبزیجات", "گوشت", "نان و لبنیات", "برنج و حبوبات"]),
    ("رستوران و کافه", 4, 9, 150_000, 600_000, ["ناهار کاری", "شام بیرون", "قهوه", "فست‌فود", "چای و کیک"]),
    ("حمل‌ونقل", 6, 12, 80_000, 320_000, ["تاکسی", "اسنپ", "بنزین", "مترو", "اتوبوس"]),
    ("خرید", 1, 3, 350_000, 1_900_000, ["لوازم خانه", "هدفون", "شارژر", "ظرف و ظروف"]),
    ("پوشاک", 0, 2, 400_000, 1_300_000, ["پیراهن", "کفش", "شلوار"]),
    ("قبض‌ها", 3, 5, 150_000, 650_000, ["برق", "گاز", "آب", "اینترنت", "تلفن همراه"]),
    ("سلامت", 0, 2, 200_000, 900_000, ["دارو", "ویزیت پزشک", "آزمایشگاه"]),
    ("سرگرمی", 1, 4, 120_000, 750_000, ["سینما", "بازی", "کنسرت", "کتاب دیجیتال"]),
    ("آموزش", 0, 2, 400_000, 1_600_000, ["دوره آنلاین", "کتاب", "کلاس زبان"]),
    ("اشتراک‌ها", 2, 4, 80_000, 300_000, ["سرویس ابری", "اسپاتیفای", "نتفلیکس"]),
    ("مراقبت شخصی", 1, 3, 150_000, 700_000, ["آرایشگاه", "باشگاه", "محصولات مراقبتی"]),
]

# Fixed monthly commitments, created once per month.
FIXED_EXPENSES = [
    ("مسکن", 24_000_000, 24_000_000, "اجاره ماهانه"),
    ("سلامت", 1_400_000, 1_400_000, "بیمه تکمیلی"),
    ("اشتراک‌ها", 250_000, 250_000, "اشتراک اینترنت پرسرعت"),
]

INCOME_SOURCES = [
    ("حقوق", 38_000_000, 46_000_000, "حقوق ماهانه"),
    ("درآمد آزاد", 4_000_000, 14_000_000, "پروژه آزاد"),
    ("سود بانکی", 800_000, 1_600_000, "سود سپرده"),
]


class Command(BaseCommand):
    help = "ایجاد داده نمونه واقع‌گرایانه برای حساب نمایشی"

    def add_arguments(self, parser):
        parser.add_argument("--email", default="demo@mymoney.ir", help="ایمیل حساب نمایشی")
        parser.add_argument("--password", default="demo12345", help="رمز عبور حساب نمایشی")
        parser.add_argument(
            "--months", type=int, default=6, help="تعداد ماه‌های گذشته برای تولید داده"
        )

    @staticmethod
    def _purge(email: str) -> None:
        """Remove an existing demo account and everything that hangs off it.

        ``Transaction.category`` uses ``on_delete=PROTECT`` on purpose: deleting
        a category must never silently destroy financial history. The flip side
        is that ``User.delete()`` cannot cascade through it, so the demo user
        cannot be removed while transactions still point at its categories.

        Deleting in dependency order — children before parents — sidesteps the
        protection without weakening it. Each queryset is scoped through the
        user's own rows so this can never touch another account's data.
        """
        existing = User.objects.filter(email=email).first()
        if existing is None:
            return

        # Leaf-most first. Transactions reference categories, so they go first;
        # budgets reference categories too, and budget items reference budgets.
        BudgetItem.objects.filter(budget__user=existing).delete()
        Budget.objects.filter(user=existing).delete()
        Transaction.objects.filter(user=existing).delete()

        # These cascade cleanly on their own but being explicit keeps the order
        # obvious and avoids relying on cascade chains for correctness.
        DebtPayment.objects.filter(debt__user=existing).delete()
        Debt.objects.filter(user=existing).delete()
        AssetValuation.objects.filter(asset__user=existing).delete()
        Asset.objects.filter(user=existing).delete()
        Account.objects.filter(user=existing).delete()
        Tag.objects.filter(user=existing).delete()

        # Categories are now unreferenced (children first, then parents).
        Category.objects.filter(user=existing, parent__isnull=False).delete()
        Category.objects.filter(user=existing).delete()

        existing.delete()

    @transaction.atomic
    def handle(self, *args, **options):
        email = options["email"].lower().strip()
        password = options["password"]
        months = max(1, min(options["months"], 12))

        rng = random.Random(SEED)

        self.stdout.write("پاک‌سازی داده‌های قبلی حساب نمایشی...")
        self._purge(email)

        user = User.objects.create_user(
            email=email,
            password=password,
            first_name="رضا",
            last_name="محمدی",
            display_name="رضا",
        )

        self.stdout.write("ایجاد دسته‌بندی‌های پیش‌فرض...")
        seed_default_categories(user)

        categories = {
            c.name: c
            for c in Category.objects.filter(user=user, kind=CategoryKind.EXPENSE)
        }
        income_categories = {
            c.name: c
            for c in Category.objects.filter(user=user, kind=CategoryKind.INCOME)
        }

        # ------------------------------------------------------------------
        # Accounts
        # ------------------------------------------------------------------
        self.stdout.write("ایجاد حساب‌ها...")
        bank = Account.objects.create(
            user=user,
            name="بانک ملت",
            account_type=AccountType.BANK,
            opening_balance=Decimal("18000000"),
            institution="بانک ملت",
            icon="landmark",
            color="blue",
            sort_order=0,
        )
        wallet = Account.objects.create(
            user=user,
            name="کیف پول نقدی",
            account_type=AccountType.CASH,
            opening_balance=Decimal("2500000"),
            icon="wallet",
            color="green",
            sort_order=1,
        )
        saman = Account.objects.create(
            user=user,
            name="بانک سامان",
            account_type=AccountType.BANK,
            opening_balance=Decimal("35000000"),
            institution="بانک سامان",
            icon="credit-card",
            color="purple",
            sort_order=2,
        )

        accounts = [bank, wallet, saman]
        # Weighted so most spending lands on the main bank account.
        account_weights = [0.65, 0.2, 0.15]

        # ------------------------------------------------------------------
        # Tags
        # ------------------------------------------------------------------
        tags = {
            name: Tag.objects.create(user=user, name=name, color=color)
            for name, color in [
                ("سفر", "blue"),
                ("کاری", "purple"),
                ("خانواده", "rose"),
                ("ضروری", "red"),
            ]
        }

        # ------------------------------------------------------------------
        # Transactions
        # ------------------------------------------------------------------
        year, month = current_jalali_month()
        today = dt.date.today()

        total_created = 0
        tag_pool = list(tags.values())

        for offset in range(months - 1, -1, -1):
            target_year, target_month = add_jalali_months(year, month, -offset)
            first_day, last_day = jalali_month_bounds(target_year, target_month)

            # Never generate transactions in the future.
            month_end = min(last_day, today)
            if month_end < first_day:
                continue

            span = (month_end - first_day).days + 1

            # For the month in progress, scale the *volume* of spending to how
            # much of the month has actually passed. Without this a demo run on
            # the 2nd of the month would show a full month of spending crammed
            # into two days, and every budget would read as blown. Partial
            # months get proportionally fewer transactions, so the dashboard
            # shows a believable "so far this month" picture on any run date.
            days_in_target_month = (last_day - first_day).days + 1
            is_partial = month_end < last_day
            month_factor = (
                max(0.25, span / days_in_target_month) if is_partial else 1.0
            )

            def scaled(count_min: int, count_max: int) -> int:
                """Reduce a per-month count range for a partial month."""
                if not is_partial:
                    return rng.randint(count_min, count_max)
                return rng.randint(
                    max(1, int(round(count_min * month_factor))),
                    max(1, int(round(count_max * month_factor))),
                )

            def random_day() -> dt.date:
                return first_day + dt.timedelta(days=rng.randrange(span))

            # --- Income ------------------------------------------------
            for cat_name, low, high, description in INCOME_SOURCES:
                category = income_categories.get(cat_name)
                if category is None:
                    continue
                # Not every side income arrives every month.
                if cat_name != "حقوق" and rng.random() < 0.45:
                    continue

                amount = Decimal(rng.randrange(low, high, 50_000))
                Transaction.objects.create(
                    user=user,
                    transaction_type=TransactionType.INCOME,
                    amount=amount,
                    category=category,
                    account=bank if cat_name == "حقوق" else rng.choice(accounts),
                    occurred_on=min(
                        first_day + dt.timedelta(days=rng.randrange(0, min(6, span))),
                        month_end,
                    ),
                    description=description,
                )
                total_created += 1

            # --- Fixed expenses ----------------------------------------
            for cat_name, low, high, description in FIXED_EXPENSES:
                category = categories.get(cat_name)
                if category is None:
                    continue
                amount = Decimal(rng.randrange(low, high + 1, 100_000))
                Transaction.objects.create(
                    user=user,
                    transaction_type=TransactionType.EXPENSE,
                    amount=amount,
                    category=category,
                    account=bank,
                    occurred_on=min(first_day + dt.timedelta(days=rng.randrange(0, 4)), month_end),
                    description=description,
                    note="پرداخت خودکار",
                )
                total_created += 1

            # --- Variable expenses -------------------------------------
            for cat_name, count_min, count_max, low, high, descriptions in EXPENSE_PATTERN:
                category = categories.get(cat_name)
                if category is None:
                    continue

                # Some categories have their own subcategories; use them
                # sometimes so the parent-rollup logic is exercised.
                children = list(category.children.all())
                target_category = category
                if children and rng.random() < 0.4:
                    target_category = rng.choice(children)

                # Skip a category entirely some months, which is realistic and
                # keeps the month-over-month comparisons interesting.
                if rng.random() < 0.12:
                    continue

                for _ in range(scaled(count_min, count_max)):
                    amount = Decimal(rng.randrange(low, high, 10_000))
                    transaction = Transaction.objects.create(
                        user=user,
                        transaction_type=TransactionType.EXPENSE,
                        amount=amount,
                        category=target_category,
                        account=rng.choices(accounts, weights=account_weights, k=1)[0],
                        occurred_on=random_day(),
                        description=rng.choice(descriptions),
                    )
                    total_created += 1

                    # Attach a tag occasionally.
                    if rng.random() < 0.12:
                        transaction.tags.add(rng.choice(tag_pool))

        self.stdout.write(f"  {total_created} تراکنش ثبت شد.")

        # ------------------------------------------------------------------
        # Budgets
        # ------------------------------------------------------------------
        self.stdout.write("ایجاد بودجه‌ها...")

        # A plausible monthly envelope, aligned with the spending pattern above
        # so most categories land inside budget with a couple near the limit.
        budget_template = [
            ("خوراک", 8_000_000, True),
            ("رستوران و کافه", 3_000_000, False),
            ("حمل‌ونقل", 2_000_000, True),
            ("خرید", 2_500_000, False),
            ("پوشاک", 1_200_000, False),
            ("مسکن", 24_500_000, True),
            ("قبض‌ها", 2_200_000, True),
            ("سلامت", 1_800_000, True),
            ("سرگرمی", 1_500_000, False),
            ("آموزش", 1_200_000, False),
            ("اشتراک‌ها", 700_000, False),
            ("مراقبت شخصی", 1_200_000, False),
        ]

        for offset in range(3, -1, -1):
            target_year, target_month = add_jalali_months(year, month, -offset)

            budget = Budget.objects.create(
                user=user,
                year=target_year,
                month=target_month,
                expected_income=Decimal("48000000"),
                savings_target=Decimal("6000000"),
                investment_target=Decimal("2000000"),
                debt_payment_target=Decimal("3000000"),
                note="برنامه ماهانه خانواده",
            )

            for cat_name, amount, is_essential in budget_template:
                category = categories.get(cat_name)
                if category is None:
                    continue
                BudgetItem.objects.create(
                    budget=budget,
                    category=category,
                    amount=Decimal(amount),
                    is_essential=is_essential,
                )

        # ------------------------------------------------------------------
        # Debts
        # ------------------------------------------------------------------
        self.stdout.write("ایجاد بدهی‌ها و طلب‌ها...")

        # Instalment loan, partially repaid.
        loan = Debt.objects.create(
            user=user,
            direction=DebtDirection.PAYABLE,
            counterparty="بانک سامان",
            principal=Decimal("120000000"),
            issued_on=to_gregorian(year - 1, 3, 15),
            due_on=to_gregorian(year + 1, 3, 15),
            description="وام خرید خودرو",
            note="۳۶ قسط ماهانه، قسط ۴٬۲۰۰٬۰۰۰ تومان",
            account=bank,
        )
        for i in range(5):
            pay_year, pay_month = add_jalali_months(year, month, -(i + 1))
            DebtPayment.objects.create(
                debt=loan,
                amount=Decimal("4200000"),
                paid_on=jalali_month_bounds(pay_year, pay_month)[0] + dt.timedelta(days=4),
                note=f"قسط {i + 1}",
                account=bank,
            )

        # Money borrowed from a friend, partly returned.
        friend = Debt.objects.create(
            user=user,
            direction=DebtDirection.PAYABLE,
            counterparty="علی رضایی",
            principal=Decimal("10000000"),
            issued_on=to_gregorian(year, month - 2 if month > 2 else 1, 10),
            due_on=to_gregorian(year, month, 25),
            description="قرض از دوست",
            note="بازپرداخت تدریجی",
        )
        DebtPayment.objects.create(
            debt=friend,
            amount=Decimal("4000000"),
            paid_on=first_day if (first_day := jalali_month_bounds(year, month)[0]) else today,
            note="پرداخت اول",
            account=wallet,
        )

        # Overdue small debt — gives the insights engine something real.
        Debt.objects.create(
            user=user,
            direction=DebtDirection.PAYABLE,
            counterparty="فروشگاه لوازم خانگی",
            principal=Decimal("7500000"),
            issued_on=to_gregorian(year, month - 3 if month > 3 else 1, 5),
            due_on=today - dt.timedelta(days=12),
            description="خرید اقساطی یخچال",
            note="سررسید گذشته",
        )

        # A receivable.
        receivable = Debt.objects.create(
            user=user,
            direction=DebtDirection.RECEIVABLE,
            counterparty="سارا احمدی",
            principal=Decimal("5000000"),
            issued_on=to_gregorian(year, month - 1 if month > 1 else 1, 8),
            due_on=today + dt.timedelta(days=9),
            description="قرض به دوست",
            note="قرار بود پایان ماه برگرداند",
        )
        DebtPayment.objects.create(
            debt=receivable,
            amount=Decimal("2000000"),
            paid_on=today - dt.timedelta(days=20),
            note="بازپرداخت بخشی",
            account=saman,
        )

        # ------------------------------------------------------------------
        # Assets
        # ------------------------------------------------------------------
        self.stdout.write("ایجاد دارایی‌ها...")

        gold_fund = Asset.objects.create(
            user=user,
            name="صندوق طلا",
            asset_type=AssetType.GOLD_FUND,
            purchase_value=Decimal("120000000"),
            purchase_date=to_gregorian(year - 1, 8, 12),
            quantity=Decimal("125.000000"),
            unit="واحد",
            unit_price=Decimal("960000"),
            description="سرمایه‌گذاری میان‌مدت",
            provider="کارگزاری مفید",
            account=saman,
        )
        # A rising value history, one valuation per month.
        for offset in range(8, -1, -1):
            val_year, val_month = add_jalali_months(year, month, -offset)
            _first, month_end = jalali_month_bounds(val_year, val_month)
            valued_on = min(month_end, today)
            # Grows from 120M toward 150M with some noise.
            progress = (8 - offset) / 8
            base = 120_000_000 + int(30_000_000 * progress)
            value = base + rng.randrange(-2_000_000, 2_000_001, 100_000)
            AssetValuation.objects.create(
                asset=gold_fund,
                value=Decimal(max(value, 100_000_000)),
                valued_on=valued_on,
                note="بروزرسانی ماهانه",
            )

        stock = Asset.objects.create(
            user=user,
            name="سهام فولاد",
            asset_type=AssetType.STOCKS,
            purchase_value=Decimal("45000000"),
            purchase_date=to_gregorian(year, 2, 20),
            quantity=Decimal("2000.000000"),
            unit="سهم",
            unit_price=Decimal("22500"),
            description="سهام بورس",
            provider="کارگزاری مفید",
            account=saman,
        )
        for offset in range(4, -1, -1):
            val_year, val_month = add_jalali_months(year, month, -offset)
            _first, month_end = jalali_month_bounds(val_year, val_month)
            value = 45_000_000 + rng.randrange(-4_000_000, 9_000_000, 500_000)
            AssetValuation.objects.create(
                asset=stock,
                value=Decimal(max(value, 30_000_000)),
                valued_on=min(month_end, today),
                note="ارزش روز",
            )

        Asset.objects.create(
            user=user,
            name="سپرده کوتاه‌مدت",
            asset_type=AssetType.DEPOSIT,
            purchase_value=Decimal("60000000"),
            purchase_date=to_gregorian(year - 2, 5, 1),
            description="سپرده یک‌ساله",
            provider="بانک ملت",
            account=bank,
        )
        AssetValuation.objects.create(
            asset=Asset.objects.get(user=user, name="سپرده کوتاه‌مدت"),
            value=Decimal("66000000"),
            valued_on=today - dt.timedelta(days=15),
            note="با سود",
        )

        Asset.objects.create(
            user=user,
            name="خودروی شخصی",
            asset_type=AssetType.VEHICLE,
            purchase_value=Decimal("780000000"),
            purchase_date=to_gregorian(year - 3, 10, 5),
            description="پژو ۲۰۶ مدل ۱۳۹۹",
            provider="خرید شخصی",
        )

        Asset.objects.create(
            user=user,
            name="ارز — دلار",
            asset_type=AssetType.CURRENCY,
            purchase_value=Decimal("38000000"),
            purchase_date=to_gregorian(year, 1, 15),
            quantity=Decimal("500.000000"),
            unit="دلار",
            unit_price=Decimal("76000"),
            description="پس‌انداز ارزی",
        )

        self.stdout.write(self.style.SUCCESS("\nداده نمایشی با موفقیت ایجاد شد."))
        self.stdout.write(f"  ایمیل: {email}")
        self.stdout.write(f"  رمز عبور: {password}")
        self.stdout.write(f"  ماه‌های داده: {months}")
        self.stdout.write(f"  تراکنش‌ها: {total_created}")
