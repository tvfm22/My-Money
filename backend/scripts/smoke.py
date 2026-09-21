import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import os, django, json
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ["DJANGO_ALLOWED_HOSTS"] = "testserver,localhost,127.0.0.1"
django.setup()
from django.test import Client

c = Client()

r = c.post("/api/auth/register/", {
    "email": "test@example.com",
    "password": "StrongPass!234",
    "password_confirm": "StrongPass!234",
    "first_name": "رضا",
}, content_type="application/json")
print("register:", r.status_code)
data = r.json()
token = data.get("access")
print("  user:", data.get("user", {}).get("full_name"))

H = {"HTTP_AUTHORIZATION": f"Bearer {token}"}

r = c.get("/api/categories/", **H)
print("categories:", r.status_code, "count:", r.json()["count"])

r = c.post("/api/accounts/", json.dumps({
    "name": "بانک ملت", "account_type": "bank", "opening_balance": "5000000"
}), content_type="application/json", **H)
print("account create:", r.status_code, r.json().get("name"), r.json().get("balance_display"))

r = c.get("/api/categories/?kind=expense&top_level=true", **H)
food = next(x for x in r.json()["results"] if x["name"] == "خوراک")
print("food category id:", food["id"])

r = c.post("/api/transactions/", json.dumps({
    "transaction_type": "expense", "amount": "250000",
    "category": food["id"], "occurred_on": "2026-09-20",
    "description": "ناهار", "tag_names": ["کاری"],
}), content_type="application/json", **H)
print("tx create:", r.status_code)
tx = r.json()
print("  amount_display:", tx.get("amount_display"))
print("  date_display  :", tx.get("date_display"))
print("  title         :", tx.get("title"))
print("  tags          :", [t["name"] for t in tx.get("tags", [])])

r = c.post("/api/transactions/", json.dumps({
    "transaction_type": "income", "amount": "1000",
    "category": food["id"], "occurred_on": "2026-09-20",
}), content_type="application/json", **H)
print("mismatched kind rejected:", r.status_code, r.json().get("errors", {}).get("category"))

r = c.get("/api/transactions/?period=this_month", **H)
print("this_month filter:", r.status_code, "count:", r.json()["count"])
print("summary:", c.get("/api/transactions/summary/", **H).json())
cal = c.get("/api/transactions/calendar/", **H).json()
print("calendar:", cal["month_name"], cal["year"], "days:", len(cal["days"]))
