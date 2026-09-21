# مالی من — My-Money

A Persian (Farsi) personal finance and expense-tracking application. Fully RTL,
Jalali-calendar-first, mobile-first, and built to answer one question well:
**«وضعیت مالی من الان چطور است؟»**

Money is tracked in Iranian Toman. Figures are grouped and rendered in Latin
digits (`1,234,567 تومان`), and every date is a real Jalali date — not a
Gregorian date wearing Persian month names. The Persian numeral path still
exists behind a single switch; see `frontend/README.md`.

---

## Quick start

### With Docker

```bash
cp data/.env.example data/.env
# put a real DJANGO_SECRET_KEY in data/.env, then:
docker compose up -d --build
```

Open **http://localhost:8080**. The database starts empty — create an account
through the UI, or load the demo data with `docker compose run --rm seed`.

Full instructions, backup and production notes: **[DEPLOY.md](DEPLOY.md)**.

### Without Docker

Two terminals. The backend must be running before the frontend can fetch
anything.

```bash
# Terminal 1 — API
cd backend
python -m venv ../.venv                       # first time only
../.venv/Scripts/pip install -r requirements.txt
cp ../data/.env.example ../data/.env          # first time only
../.venv/Scripts/python manage.py migrate
../.venv/Scripts/python manage.py seed_demo   # optional demo data
../.venv/Scripts/python manage.py runserver 127.0.0.1:8000
```

```bash
# Terminal 2 — web app
cd frontend
npm install
npm run dev
```

Open **http://127.0.0.1:5173/**.

> **Which port?** The app is on **5173** (Vite). Port **8000** is the API only —
> it serves nothing but `/api/…`, so opening it in a browser gives a JSON
> notice pointing back here rather than the application. If you land on `8000`
> and see JSON, that is expected; switch to `5173`.

> **Where is my data?** Everything that persists lives in **`data/`** — the
> SQLite database, uploads, collected static files and the configuration file.
> Nothing outside that folder holds state. See [data/README.md](data/README.md).

### Demo account

After `seed_demo`:

| | |
| --- | --- |
| Email | `demo@mymoney.ir` |
| Password | `demo12345` |

It contains 7 months of realistic activity across accounts, categories,
transactions, budgets, debts (both directions) and assets. The credentials are
**not** shown on the login screen — that line was removed so the shipped UI
never advertises credentials; this table is the single reference.

---

## Is it running?

```bash
curl http://127.0.0.1:8000/api/health/   # {"status": "ok", ...}
curl -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5173/   # 200
```

`http://127.0.0.1:8000/` itself returns a short JSON notice describing the API,
by design — see the port note above.

---

## Why the browser can reach the API

Vite proxies `/api` to `http://127.0.0.1:8000` (see `frontend/vite.config.ts`),
so the frontend makes same-origin requests in development and CORS is never in
the way. The API also allows the dev origins explicitly via
`CORS_ALLOWED_ORIGINS`.

---

## Features

**Dashboard** — the answer to «وضعیت مالی من الان چطور است؟»: spendable
balance, this month's income and expense with month-over-month comparison,
assets, debts, receivables, budget consumption, and recent transactions.

**Transactions** — full CRUD, search, filters, sort, date-grouped list, and a
keypad-based quick-entry sheet that records an expense in seconds. Frequently
used categories are remembered locally.

**Budgets** — monthly allocation per category with allocated / spent /
remaining / percent / days elapsed vs. expected.

**Smart budget analysis** — compares *percent of month elapsed* against
*percent of budget consumed*, so a budget can be read as on-track or running
hot before it is exhausted. Phrasing is deliberately non-judgemental: no claim
implies guaranteed advice.

**Debts & receivables** — both directions, with partial payments, principal /
paid / remaining, due dates, and overdue detection. Statuses: فعال، بخشی پرداخت
شده، تسویه شده، سررسید گذشته.

**Assets & net worth** — bank accounts, cash, gold funds, gold, stocks,
currency, property, vehicles, deposits, and other holdings — including
quantity / unit / unit price for unit-based holdings. Net worth is assets minus
liabilities, with history and a chart.

**Reports** — spending by category, monthly trend, income vs. expense,
budget vs. actual, and net-worth history. Charts are used where they clarify,
not for decoration.

**Financial insights** — observations derived strictly from recorded data.
Nothing is invented; if there is not enough data to say something useful, it
says nothing.

---

## Design principles

These are enforced, not aspirational.

- **Jalali is computed server-side and client-side.** Dates are stored as
  Gregorian and presented as Jalali. Conversion lives in
  `backend/apps/core/jalali.py` and `frontend/src/utils/jalali.ts`.
- **Money is never a float.** `Decimal` on the server with `ROUND_HALF_UP`,
  serialized as a string. The client treats it as a string and prefers the
  server's `*_display` field so the two can never disagree.
- **Derived values are never stored.** Account balance, budget spent, debt
  status and asset current value are all computed.
- **Number formatting is exact and centrally controlled.** Numerals are Latin by
  default, driven by `USE_PERSIAN_DIGITS` in `frontend/src/utils/format.ts`. The
  Persian path (U+066C `٬`, U+066B `٫`, U+2212, `٪`) is still implemented and
  tested. Quantities are grouped; identifiers are not — a year must never render
  as `1,405`, so years go through `formatYear`.
- **Nothing is formatted at the render site.** Server `*_display` strings are
  transliterated once, in the axios response interceptor. `frontend/src/test/numerals.test.ts`
  enforces this: it fails on `toLocaleString('fa-IR')`, on a Persian digit typed
  into JSX, and on any Persian digit in the rendered output of any route.
- **Colour is never the only signal.** Every status carries text or an icon as
  well, so it survives greyscale and reaches screen readers.
- **Errors speak Persian.** A user never sees a status code or an English
  server string; untranslated messages are discarded and replaced with calm
  Persian copy.
- **Business logic lives on the server.** React renders figures; it does not
  compute them.
- **No blank screens.** Loading, error and empty states are explicit
  everywhere.

---

## Project layout

```
My-Money/
├── backend/
│   ├── apps/
│   │   ├── core/          Jalali conversion, Persian formatting, permissions,
│   │   │                  shared fields, demo seeder
│   │   ├── users/         Custom user model, auth
│   │   ├── accounts/      Bank accounts and wallets
│   │   ├── categories/    Categories and subcategories
│   │   ├── transactions/  Income and expense records
│   │   ├── budgets/       Monthly budgets and analysis
│   │   ├── debts/         Debts, receivables, partial payments
│   │   ├── assets/        Assets and valuations
│   │   ├── reports/       Aggregates and series
│   │   └── insights/      Data-derived observations
│   └── config/            Settings, URLs, custom test runner
└── frontend/
    └── src/
        ├── components/    UI primitives and shared pieces
        ├── features/      One folder per section
        ├── hooks/         Auth context and TanStack Query hooks
        ├── services/      Axios client and API modules
        ├── utils/         Jalali calendar and Persian formatting
        └── test/          Harness and test suites
```

---

## Stack

**Backend** — Django 6.1, Django REST Framework 3.18, SimpleJWT 5.5,
django-filter 26.1, django-cors-headers 4.9, python-dotenv. **SQLite** only.

**Frontend** — React 19, TypeScript 6, Vite 8, Tailwind CSS 4, TanStack Query 5,
React Hook Form 7 + Zod 4, React Router 7, Axios 1.20, Recharts 3,
lucide-react. Tests with Vitest 5 and Testing Library.

---

## Testing

```bash
# Backend — 347 tests
cd backend && ../.venv/Scripts/python.exe manage.py test

# Frontend — 212 tests
cd frontend && npx vitest run

# Typecheck
cd frontend && npx tsc -b --noEmit
```

`backend/config/test_runner.py` provides a custom discovery runner, because the
`tests` package name collides across Django apps and the default runner shadows
all but one of them.

`frontend/src/test/harness.tsx` installs a stub as a **custom axios adapter**
rather than mocking service modules, so the interceptor chain — token refresh,
error normalisation, Persian message selection — is exercised rather than
bypassed. Read its header comment before adding tests; it documents why the
obvious alternatives do not work.

Coverage includes model and API behaviour, permission and user-isolation checks,
financial calculations (budget consumption, debt amortisation, net worth),
form validation, accessible labelling of every form control, RTL and Jalali
formatting, and the critical end-to-end flows.

---

## Notes and limitations

- **No live market prices.** Asset valuations are entered manually. Wiring in a
  market-data API is deliberately out of scope until a reliable source is
  configured.
- **SQLite.** Fine for personal use and local development; a multi-user
  deployment would want a server database and a real task queue.
- **Browser automation is not available on Windows** in this environment, so
  end-to-end verification runs through HTTP-level checks and Testing Library
  rather than a driving browser.

---

## Configuration

Backend settings come from `backend/.env`:

| Variable | Purpose |
| --- | --- |
| `DJANGO_SECRET_KEY` | Signing key — **must be changed for any real deployment** |
| `DJANGO_DEBUG` | Debug mode |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated host allowlist |
| `DB_ENGINE` / `DB_NAME` | Database (SQLite) |
| `CORS_ALLOWED_ORIGINS` | Permitted frontend origins in development |

Secrets are read from the environment, never committed.
