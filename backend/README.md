# Backend — Django REST API

Persian personal finance API. Django 6.1 + DRF, JWT auth, SQLite, all money as
`Decimal`.

```bash
python -m venv ../.venv                       # from backend/, first time only
../.venv/Scripts/pip install -r requirements.txt
cp ../data/.env.example ../data/.env          # first time only
../.venv/Scripts/python manage.py migrate
../.venv/Scripts/python manage.py seed_demo
../.venv/Scripts/python manage.py runserver 127.0.0.1:8000
```

Configuration is read from **`../data/.env`**, not from this directory. That
folder is also where the database, uploads and collected static files live, so a
deployment has one thing to mount and back up. See
[`../data/README.md`](../data/README.md) and [`../DEPLOY.md`](../DEPLOY.md).

Base path is `/api/`. Interactive browsable API: visit any endpoint in a
browser while `DJANGO_DEBUG=True`.

> **This port is the API, not the app.** `http://127.0.0.1:8000/` returns a
> short JSON notice describing the API — that is intentional. The web
> interface is served by Vite on **http://127.0.0.1:5173/**.

---

## Configuration

Every environment-specific value is read from **`../data/.env`**. That folder is
also where the database, uploads and collected static files live, so a
deployment has exactly one thing to mount, back up and set permissions on.

Nothing is hardcoded and no secret is committed. The settings module reads the
file through `load_dotenv`, which does **not** overwrite variables already
present in the process environment — so `docker compose` can force
`DJANGO_DEBUG=False` without editing the file.

| Variable | Default | Notes |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | insecure placeholder | **Must** be set in production. Signs session cookies and reset tokens. |
| `DJANGO_DEBUG` | `True` | Must be `False` in production. |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated. Must include the public hostname. |
| `MY_MONEY_DATA_DIR` | `<repo>/data` | Absolute or repo-relative. `/data` in Docker. |
| `DB_ENGINE` | `sqlite` | `postgresql` is a documented seam, not a shipped path. |
| `DB_NAME` | `db.sqlite3` | A filename; always resolves inside `<DATA_DIR>/db/`. An absolute path is honoured. |
| `SQLITE_JOURNAL_MODE` | unset | `WAL` is recommended once gunicorn runs multiple workers. |
| `STATIC_ROOT` / `MEDIA_ROOT` | `<DATA_DIR>/static`, `<DATA_DIR>/media` | Override only to mount them separately. |
| `CORS_ALLOWED_ORIGINS` | localhost:5173 | Not needed in Docker — one origin serves everything. |
| `CSRF_TRUSTED_ORIGINS` | localhost:5173 | Same. |
| `ACCESS_TOKEN_LIFETIME_MINUTES` | `60` | |
| `REFRESH_TOKEN_LIFETIME_DAYS` | `14` | |
| `SECURE_SSL_REDIRECT` | `True` when `DEBUG=False` | Set `False` for plain-HTTP Docker; `True` only behind real TLS. |

The paths are resolved in `config/settings.py` by three small helpers —
`resolve_data_dir`, `sqlite_path` and `sqlite_pragmas` — each of which accepts
either an absolute or a relative value, so the same code serves a local checkout
and a container without a branch.

---

## Deployment

```bash
docker compose up -d --build     # from the repository root
```

The image runs as a non-root user, applies migrations and collects static files
on start, then hands off to gunicorn. See [`../DEPLOY.md`](../DEPLOY.md).

The entrypoint refuses to start if `DJANGO_SECRET_KEY` is unset while
`DJANGO_DEBUG` is off, and it never resets, flushes or reseeds the database.


## Apps

| App | Responsibility |
| --- | --- |
| `core` | Jalali conversion, Persian formatting, permissions, shared serializer fields, the demo seeder |
| `users` | Custom user model and authentication |
| `accounts` | Bank accounts, wallets, cards |
| `categories` | Categories and subcategories |
| `transactions` | Income and expense records |
| `budgets` | Monthly budgets, items, and analysis |
| `debts` | Debts, receivables, partial payments |
| `assets` | Assets and valuation history |
| `reports` | Aggregates and time series |
| `insights` | Observations derived from recorded data |

---

## The rules this codebase follows

### Money

Every monetary field is a `DecimalField`, never a float. Arithmetic uses
`ROUND_HALF_UP`. Values are serialized as **strings** with a `*_display`
sibling holding the Persian-formatted version:

```json
{ "amount": "123456.00", "amount_display": "۱۲۳٬۴۵۶ تومان" }
```

The client prefers `*_display`, so the two sides cannot disagree about how a
number should look.

### Dates

Dates are stored Gregorian and presented Jalali. `occurred_on` is always an ISO
Gregorian string; `jalali_date`, `date_display` and `date_short` are derived for
display. Input accepts Jalali too — `JalaliDateField` parses `1405-06-29`,
`1405/06/29`, `۱۴۰۵/۰۶/۲۹`, and Gregorian ISO, disambiguating on a year ceiling
of 1700.

`core/jalali.py` implements the conversion from first principles (Julian Day
Number arithmetic with the 33-year leap cycle) rather than pulling in a
dependency, so the behaviour is identical on both sides of the wire and does
not vary between environments.

### Spending classification

Every expense carries a user-chosen `spending_type`: `essential`, `flexible` or
`wasted` (`transactions.SpendingType`). Income never does — the serializer
rejects the field on income, and `save()` normalises: an expense defaults to
`flexible` when omitted, an income has the field cleared. It is filterable
(`?spending_type=…`) and aggregates read it through `spending_type_breakdown` /
`spending_type_by_category` in `transactions/services.py`, which feed the
dashboard's `spending_types` block and the reports payload's
`spending_by_type` plus the per-row `spending_types` on `budget_vs_actual`.

This is the **only** essential/flexible split the interface shows. There used to
be a second one: `BudgetItem.is_essential`, which classified a *budget line*
rather than an expense and fed `plan.essential_total` / `plan.flexible_total` on
the budget analysis. Both were labelled «ضروری» on different screens while
measuring different things, so the same word meant two different numbers. The
budget page's version was removed from the UI on 2026-09-21.

The API still carries it — the flag, the column and the two payload fields all
exist, and the plan endpoint still accepts `is_essential` per allocation. Nothing
in the interface reads or sends it. Treat it as reserved, not as a feature: a new
client should use `spending_type` instead.

### Derived, never stored

Account balance, budget spent, debt status and asset current value are all
computed on read. Storing them would mean a denormalisation bug is a wrong
number on the dashboard.

### Authorisation

Permissions are deny-by-default. Every queryset is scoped with `for_user(user)`
as the primary isolation boundary, and `IsOwner` implements **both**
`has_permission` and `has_object_permission`.

> The `has_permission` half matters: setting `permission_classes = [IsOwner]`
> *replaces* the global `IsAuthenticated` default. Omitting it silently makes
> an endpoint public.

### Errors

Validation failures return Persian messages with per-field detail:

```json
{
  "detail": "اطلاعات ارسالی نامعتبر است.",
  "errors": { "amount": ["این مقدار باید بزرگ‌تر یا مساوی با 0.01 باشد."] }
}
```

---

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/auth/register/` | Create an account |
| POST | `/api/auth/login/` | Obtain access + refresh tokens |
| POST | `/api/auth/token/refresh/` | Rotate the access token |
| POST | `/api/auth/logout/` | Blacklist the refresh token |
| GET/PATCH | `/api/auth/me/` | Current user profile |
| GET | `/api/dashboard/` | Everything the dashboard needs, in one call |
| GET/POST | `/api/transactions/` | List (paginated) and create |
| GET/PATCH/DELETE | `/api/transactions/{id}/` | Retrieve, update, delete |
| GET | `/api/transactions/recent/` | Recent activity |
| GET | `/api/transactions/summary/` | Period totals |
| GET/POST | `/api/categories/` | Categories |
| GET | `/api/categories/picker/?kind=` | Flat list for pickers |
| GET | `/api/categories/grouped/` | Parent/child tree |
| GET | `/api/categories/meta/` | Available icons and colours |
| GET/POST | `/api/accounts/` | Accounts and wallets |
| GET | `/api/accounts/picker/` | Flat list for pickers |
| GET/POST | `/api/budgets/` | Monthly budgets |
| GET | `/api/budgets/performance/` | Month-elapsed vs. budget-consumed analysis |
| GET/POST | `/api/debts/` | Debts and receivables |
| POST | `/api/debts/{id}/payments/` | Record a partial payment |
| GET/POST | `/api/assets/` | Assets |
| POST | `/api/assets/{id}/valuations/` | Record a valuation |
| GET | `/api/net-worth/` | Current net worth and history |
| GET | `/api/reports/` | All report sections in one payload |
| GET | `/api/reports/spending-by-category/` | Category breakdown |
| GET | `/api/reports/monthly-trend/?months=` | Income/expense series |
| GET | `/api/reports/budget-vs-actual/` | Budget against actual |
| GET | `/api/insights/` | Derived observations |

### Selecting a month

Any endpoint that is month-scoped (`/budgets/analysis/`, `/budgets/current/`,
`/budgets/performance/`, `/insights/`, `/reports/`, `/transactions/calendar/`)
resolves its month through one shared helper,
`apps.core.jalali.resolve_month_param`. Three spellings are accepted:

| Spelling | Example |
| --- | --- |
| Packed | `?month=1405-06` (also `1405/06`) |
| Year + month | `?year=1405&month=6` — what the web client sends |
| Legacy | `?year=1405&month_number=6` |

Anything unparseable or out of range falls back to the **current** Jalali month
rather than erroring. That fallback is deliberate — a malformed filter should
render something rather than a 500 — but it is also why this helper exists in one
place. The parsing was once copy-pasted into four views, and the copies drifted:
they understood only the packed form, so `?year=&month=` was silently ignored and
the UI appeared not to filter at all. Add a new month-scoped endpoint by calling
the helper, not by re-implementing the parse.

The month label (`شهریور ۱۴۰۵`) likewise comes from one place,
`apps.core.jalali.month_label`, so a month with a budget and one without are
labelled identically.

---

## Tests

```bash
../.venv/Scripts/python.exe manage.py test
```

347 tests across the apps, covering models, API behaviour, permissions,
user isolation, and the financial calculations specifically.

### The custom test runner

`config.test_runner.AppAwareDiscoverRunner` exists because every app has a
`tests` package with the same basename. Django's default discovery imports them
by that name, so all but one is shadowed — you get a green run that silently
tested one app. The runner enumerates `apps.*.tests` explicitly via `pkgutil`
and imports each under a unique module path.

If you add a new app with tests, no registration is needed — discovery is
dynamic. But **do not remove the runner** without understanding the above.

---

## The demo seeder

```bash
../.venv/Scripts/python manage.py seed_demo
```

Idempotent. It purges the demo user's existing data in dependency order, then
rebuilds: default categories (including subcategories), accounts, budgets,
debts in both directions, assets across all types, and roughly seven months of
transactions.

The current month is deliberately scaled to the elapsed fraction of the month,
so the dashboard's budget analysis has a realistic mid-month reading instead of
a full month's spending on day three.

Other users are never touched.
