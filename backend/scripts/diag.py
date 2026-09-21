import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ["DJANGO_ALLOWED_HOSTS"] = "testserver,localhost"
import django; django.setup()
import traceback
from django.contrib.auth import get_user_model
from apps.budgets.models import Budget
from apps.budgets.services import analyse_budget
from apps.insights.views import generate_insights

U = get_user_model()
u = U.objects.get(email="demo@mymoney.ir")
from apps.core.jalali import current_jalali_month
y, m = current_jalali_month()
print("today month:", y, m)
bud = Budget.objects.for_user(u).filter(year=y, month=m).first()
print("budget found:", bud)
if bud:
    a = analyse_budget(u, bud)
    print("categories in analysis:", len(a.categories))
    print("payload categories:", len(a.to_dict()["categories"]))
    for c in a.categories[:3]:
        print("   ", c.category_name, c.consumed_percent)
print()
print("all budgets:", list(Budget.objects.for_user(u).values_list("year","month")))
print()
try:
    ins = generate_insights(u, year=y, month=m)
    print("insights:", len(ins))
except Exception:
    traceback.print_exc()
