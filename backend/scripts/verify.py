import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ["DJANGO_ALLOWED_HOSTS"] = "testserver,localhost,127.0.0.1"
import django
django.setup()
from django.test import Client

c = Client()
r = c.post("/api/auth/login/", {"email": "demo@mymoney.ir", "password": "demo12345"},
           content_type="application/json")
print("login:", r.status_code)
tok = r.json()["access"]
H = {"HTTP_AUTHORIZATION": f"Bearer {tok}"}

print("\n===== DASHBOARD =====")
r = c.get("/api/dashboard/", **H)
print("status:", r.status_code)
d = r.json()
print("month:", d["month"]["label"], "|", d["month"]["elapsed_display"], "elapsed")
s = d["summary"]
print(f'  موجودی کل      : {s["balance_display"]}')
print(f'  درآمد این ماه  : {s["income_display"]}')
print(f'  هزینه این ماه  : {s["expense_display"]}')
print(f'  مانده قابل خرج : {s["spendable_display"]}')
print(f'  ارزش دارایی‌ها  : {s["total_assets_display"]}')
print(f'  بدهی‌های من     : {s["total_debts_display"]}')
print(f'  طلب‌های من      : {s["total_receivables_display"]}')
print(f'  ارزش خالص      : {s["net_worth_display"]}')
print("  expense vs last month:", d["comparison"]["expense"]["direction"], d["comparison"]["expense"]["percent_display"])
b = d["budget"]
print(f'  بودجه {b["label"]}: {b["totals"]["consumed_display"]} مصرف شده')
print(f'    بودجه   : {b["totals"]["budgeted_display"]}')
print(f'    هزینه   : {b["totals"]["spent_display"]}')
print(f'    باقی    : {b["totals"]["remaining_display"]}')
print("  top budget categories:")
for cat in b["top_categories"]:
    print(f'    {cat["category_name"]:<18} {cat["consumed_display"]:>5}  {cat["status_label"]}')
print("  recent transactions:", len(d["recent_transactions"]))
for t in d["recent_transactions"][:4]:
    print(f'    {t["date_short"]:<20} {t["title"]:<22} {t["amount_display"]}')

print("\n===== BUDGET PERFORMANCE =====")
r = c.get("/api/budgets/performance/", **H)
p = r.json()
print("status:", r.status_code, "| summary:", p["summary"])
for cat in p["categories"][:6]:
    print(f'  {cat["category_name"]:<18} بودجه {cat["budgeted"]:>12} مصرف {cat["spent"]:>12} '
          f'باقی {cat["remaining"]:>12} {cat["consumed_display"]:>5} {cat["status_label"]}')
    print(f'      → {cat["message"]}')

print("\n===== INSIGHTS =====")
r = c.get("/api/insights/", **H)
ins = r.json()
print("status:", r.status_code, "count:", ins["count"])
for i in ins["insights"]:
    print(f'  [{i["severity"]:>9}] {i["title"]}')
    print(f'      {i["message"]}')

print("\n===== REPORTS =====")
r = c.get("/api/reports/", **H)
rep = r.json()
print("status:", r.status_code)
sc = rep["spending_by_category"]
print("spending by category: total", sc["total_display"], "slices", len(sc["slices"]))
for sl in sc["slices"][:5]:
    print(f'   {sl["name"]:<22} {sl["total_display"]:>20} {sl["share_display"]}')
print("monthly trend:", len(rep["monthly_trend"]["series"]), "months")
for m in rep["monthly_trend"]["series"]:
    print(f'   {m["label"]:<10} in {m["income"]:>12} out {m["expense"]:>12} net {m["net"]:>13}')
print("net worth history:", len(rep["net_worth_history"]["history"]), "points")
for h in rep["net_worth_history"]["history"][-4:]:
    print(f'   {h["label"]}  assets {h["assets"]:>12} liab {h["liabilities"]:>11} net {h["net_worth"]:>13}')
print("asset breakdown:", [(x["label"], x["total_display"]) for x in rep["asset_breakdown"][:4]])

print("\n===== DEBTS =====")
r = c.get("/api/debts/summary/", **H)
ds = r.json()
print("status:", r.status_code)
print("  بدهی‌های من   :", ds["payable_remaining_display"], f'({ds["open_count"]} open)')
print("  طلب‌های من    :", ds["receivable_remaining_display"])
print("  سررسید گذشته :", ds["overdue_count"], "مورد |", ds["overdue_amount_display"])
print("  upcoming:", len(ds["upcoming"]))
for u in ds["upcoming"][:3]:
    print(f'    {u["counterparty"]:<24} {u["remaining_display"]:>18} {u["status_label"]} ({u["due_relative"]})')

print("\n===== ASSETS =====")
r = c.get("/api/assets/summary/", **H)
a = r.json()
print("status:", r.status_code)
print("  ارزش فعلی :", a["current_value_display"])
print("  ارزش خرید :", a["purchase_value_display"])
print("  بازده اسمی:", a["nominal_return_display"], f'({a["nominal_return_percent_display"]})')
print("  net worth:", a["net_worth"]["net_worth_display"])

print("\n===== ISOLATION CHECK =====")
# Register a second account that owns no financial data, then confirm it cannot
# see the demo account's rows. If the account already exists from an earlier
# run, log in instead so the script stays re-runnable.
intruder_email = "intruder@x.com"
intruder_password = "StrongPass!234"

r2 = c.post(
    "/api/auth/register/",
    {
        "email": intruder_email,
        "password": intruder_password,
        "password_confirm": intruder_password,
    },
    content_type="application/json",
)
if r2.status_code >= 400:
    r2 = c.post(
        "/api/auth/login/",
        {"email": intruder_email, "password": intruder_password},
        content_type="application/json",
    )
if r2.status_code >= 400:
    print("  ! could not authenticate intruder account:", r2.status_code, r2.content[:200])
else:
    H2 = {"HTTP_AUTHORIZATION": f'Bearer {r2.json()["access"]}'}
    for ep in ["/api/transactions/", "/api/debts/", "/api/assets/", "/api/budgets/"]:
        rr = c.get(ep, **H2)
        body = rr.json()
        cnt = body.get("count", len(body) if isinstance(body, list) else "?")
        flag = "OK" if cnt in (0, "0") else "LEAK"
        print(f"  [{flag:>4}] intruder sees {ep:<26} count={cnt}")
