"""Ad-hoc: inspect the seeded budget distribution for the demo account."""

import os
import sys
from collections import Counter

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.budgets.models import Budget  # noqa: E402
from apps.budgets.services import analyse_budget, empty_analysis  # noqa: E402
from apps.core.jalali import (  # noqa: E402
    current_jalali_month,
    format_money,
    format_percent,
)
from apps.users.models import User  # noqa: E402

user = User.objects.get(email="demo@mymoney.ir")
year, month = current_jalali_month()
budget = Budget.objects.filter(user=user, year=year, month=month).first()
analysis = (
    analyse_budget(user, budget) if budget else empty_analysis(user, year, month)
)

tally = Counter(c.status for c in analysis.categories)
print("status tally:", dict(tally))
print(
    "total  :",
    format_money(analysis.total_budgeted),
    "/",
    format_money(analysis.total_spent),
    f"({format_percent(analysis.total_consumed_percent)})",
)
print("elapsed:", format_percent(analysis.elapsed_percent))
print("actuals: income", analysis.actual_income, "expense", analysis.actual_expense)
print()
for c in analysis.categories:
    print(
        f"  {c.category_name:<18} {c.status:<11}"
        f"  {format_percent(c.consumed_percent):>8}"
        f"   {format_money(c.budgeted):>18} / {format_money(c.spent):>18}"
    )
