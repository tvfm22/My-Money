import os, sys, django, json, datetime as dt
from decimal import Decimal

sys.path.insert(0, os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ["DJANGO_ALLOWED_HOSTS"] = "testserver,localhost,127.0.0.1"
django.setup()
from rest_framework.test import APIClient
from apps.users.models import User
u = User.objects.get(email="demo@mymoney.ir")
c = APIClient(); c.force_authenticate(u)
def show(label, path):
    r = c.get(path)
    print("="*20, label, path, r.status_code)
    d = r.data
    if isinstance(d, list):
        print("LIST len", len(d), "first:", json.dumps(d[0], ensure_ascii=False)[:400] if d else None)
    else:
        print("KEYS:", list(d.keys()))
        print(json.dumps(d, ensure_ascii=False, default=str)[:700])
for lbl, p in [
    ("summary","/api/transactions/summary/"),
    ("recent","/api/transactions/recent/?limit=5"),
    ("trend","/api/reports/monthly-trend/?months=6"),
    ("asset","/api/assets/summary/"),
]:
    show(lbl, p)
