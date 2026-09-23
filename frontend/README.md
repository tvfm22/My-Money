# Frontend — React + TypeScript

The web client for **مالی من**, a Persian personal finance app. RTL throughout,
Jalali calendar, mobile-first.

```bash
npm install
npm run dev      # http://127.0.0.1:5173
npm test         # vitest, 212 tests
npm run build    # production bundle
npx tsc -b       # typecheck
```

The dev server proxies `/api` to `http://127.0.0.1:8000`, so start the Django
backend first.

---

## Structure

```
src/
├── components/
│   ├── ui/          Primitives: Button, Input, Select, Modal, BottomSheet,
│   │                Card, Badge, ProgressBar, JalaliDatePicker, Toast, states
│   ├── common/      MoneyDisplay, TransactionItem, CategoryIcon, BudgetProgress
│   └── layout/      PageHeader, MonthNavigator
├── config/          Navigation model
├── features/        One folder per section (dashboard, transactions, budgets,
│                    debts, assets, reports, insights, settings, auth)
├── hooks/           AuthProvider, ThemeProvider, all TanStack Query hooks
├── layouts/         AppShell — sidebar, bottom nav, quick-add
├── services/        Axios client and typed API modules
├── types/           The API type surface
├── utils/           jalali.ts, format.ts, chartPalette.ts
└── test/            Harness and suites
```

---

## Conventions

### Spending classification

Every expense carries one of three user-chosen types: `essential` (ضروری),
`flexible` (انعطاف‌پذیر), `wasted` (غیرضروری). Income never carries one — the
server rejects the field. The picker is shared (`components/common/
SpendingTypeSelector.tsx`) so the quick sheet and the full form always offer
the same three options. The month-level split renders through
`components/common/SpendingTypeSplit.tsx` (dashboard and reports); per-category
splits appear on the report rows and a category's itemised expenses open from
the budgets page (`CategoryDrillDown`). The label is judgement-free by design —
never phrase wasted spending as a fault.

### Jalali dates

Store and transport ISO Gregorian strings; convert at the edges. A Gregorian
date must never reach the screen — and a date is not a quantity, so it is never
grouped or rounded.

```ts
import { formatJalali, toJalali, jalaliToIso } from '../utils/jalali'

formatJalali('2026-09-20', 'long')  // '29 شهریور 1405'
formatJalali('2026-09-20', 'full')  // 'یکشنبه 29 شهریور 1405'
```

Month and weekday names stay Persian; only the digits follow the numeral style
below.

`JalaliDatePicker` takes and returns **Gregorian ISO**; it only looks Jalali.

### Numbers and money

All of it goes through `utils/format.ts`:

```ts
formatNumber(1234567)             // '1,234,567'
formatMoney(250000)               // '250,000 تومان'
formatMoney(-250000)              // '−250,000 تومان'
formatPercent(65)                 // '65%'
formatDigits(12500000)            // '12,500,000'
formatYear(1405)                  // '1405'  — never grouped
formatAmountForInput('1234.5')    // '1,234.5'  — for <input> values
```

**Numerals are Latin by default.** A single switch controls it:
`USE_PERSIAN_DIGITS` in `utils/format.ts`. Every formatter defaults its `latin`
option from that constant, so flipping it changes the whole product. The Persian
path still exists — `formatMoney(250000, { latin: false })` gives
`'۲۵۰٬۰۰۰ تومان'` with U+066C separators — and is covered by tests, because it
is what a future locale switch would turn on.

Two rules that are easy to get wrong:

- **Quantities get grouped; identifiers do not.** A year must never be grouped:
  `formatDigits(1405)` renders `1,405`, which is nonsense on screen. Use
  `formatYear` for years and never route a date through `formatDigits`.
- **Never type a numeral literally into JSX.** `placeholder="۰"` bypasses every
  formatter and kept rendering Persian long after the switch flipped. Use
  `ZERO_PLACEHOLDER`, `MIN_PASSWORD`, or `formatDigits(...)` in a template.

Both rules are enforced by `src/test/numerals.test.ts`, which fails on a
locale-dependent formatter (`toLocaleString('fa-IR')`), on a Persian digit
literal outside the two conversion tables, and on any Persian digit in the
rendered output of every route. Three `toLocaleString('fa-IR')` call sites
survived the switch to Latin digits and were only found by reading a rendered
page; the source scan is what stops that recurring.

Server-provided `*_display` strings are built with Persian digits on the
backend. The axios response interceptor runs `latinizeDeep` over every payload,
so they are converted once at the API boundary rather than at ~50 render sites.
`latinize` rewrites the separators as well (U+066C → `,`, U+066B → `.`) —
digits alone would produce the worst-of-both `250٬000`.

`Intl` is deliberately unused: its `fa-IR` currency output places the unit
differently across browsers.

`MoneyDisplay` should be preferred over calling `formatMoney` directly, because
it also handles sign colouring and the `ltr-nums` isolation that keeps an RTL
sentence from mangling a number.

### Text direction

The document is `dir="rtl"`. Two classes do the heavy lifting:

- `ltr-nums` — wraps a figure in `unicode-bidi: isolate` so a number with a
  sign, a decimal point or a date reads correctly inside RTL prose.
- `pb-bottom-nav` — safe-area padding so content clears the mobile bottom nav
  and the home indicator.

Tailwind logical properties (`ps-`, `pe-`, `start-`, `end-`) are used instead of
left/right so the layout is direction-agnostic.

### Accessibility

- Every form control has an accessible name. `Input` and `Select` fall back to
  `useId()` when no `id` or `name` is given; `JalaliDatePicker` does the same.
  **Never hardcode a fallback `id`** — two instances on one form then collide,
  and the second label silently points at the first control.
- Colour is never the only carrier of meaning. Status always travels with text
  or an aria-labelled label.
- Icons are Lucide, never emoji.
- Dialogs and popovers are announced (`role="dialog"`), close on Escape, lock
  body scroll, and keep keyboard focus inside via `useDialogA11y` — which also
  restores focus to the trigger on close. The `BottomSheet` grab area is a real
  swipe-to-dismiss surface.

### Feedback

Saves and deletes confirm themselves through the **toast system**
(`components/ui/Toast.tsx`): a polite live region above the bottom nav, with an
optional undo action — deleting a transaction offers «بازگردانی», which
re-creates the row from its fields. Inline form feedback (settings) stays
inline; the toast is for outcomes of *closed* dialogs.

### Theming

Light and dark are the **same tokens, twice**. `index.css` declares the palette
in `@theme` and redefines every token under `.dark`; the class lives on `<html>`,
toggled by `ThemeProvider` (localStorage `mymoney.theme`, falling back to the OS
preference) and pre-applied by a tiny inline script in `index.html` so a
dark-mode user never sees a white flash. Components never branch on the theme —
they consume tokens, which is why the switch is one class.

Recharts cannot resolve CSS variables in SVG attributes, so
`utils/chartPalette.ts` mirrors the chart-relevant tokens as TypeScript
constants (`LIGHT_CHART` / `DARK_CHART`). **When a chart-relevant token changes,
change its twin there.** The pairing is documented in both files.

### Fonts

Vazirmatn is **self-hosted** from `public/fonts/` (the four weights the UI uses,
~50 kB each) — no CDN dependency, correct rendering offline. Add a weight only
if a design actually needs it; every weight ships to every user.

---

## Data flow

TanStack Query owns all server state. Query keys are centralised in
`hooks/queries.ts`, and mutations invalidate across resources — creating a
transaction refreshes the dashboard, the budget figures and the account
balance, because all three are derived from it.

```ts
const { data, isPending, isError } = useDashboard()
```

Every screen handles four states explicitly: **loading, error, empty, ready**.
There is no blank screen. Skeletons mirror the eventual layout so the page does
not jump when data lands.

---

## The API client

`services/client.ts` wraps axios with:

- JWT in local storage via `tokenStore`
- **Single-flight refresh** — concurrent 401s share one refresh request, and
  each queued request is replayed once it resolves
- `normalizeError` — turns anything thrown into a Persian `ApiError`
- `errorMessage` / `fieldErrors` — for form-level and field-level display

### Two things to know before changing it

**The response interceptor rejects with a normalised `ApiError`, not the raw
axios error.** It is a plain object, not an `Error` subclass. `normalizeError`
therefore checks for that shape first; without that branch, any caller doing
`normalizeError(errorMessage(error))` — which is the normal pattern — falls
through to the generic fallback and **silently discards the server's Persian
message**.

**A server `detail` is only trusted if it contains Persian characters.** An
untranslated `"Internal Server Error"` must not reach the screen, so anything
without Persian script is replaced with local copy.

---

## Tests

```bash
npm test                              # all suites
npx vitest run src/test/a11y.test.tsx # one suite
```

| Suite | Tests | Covers |
| --- | --- | --- |
| `format.test.ts` | 45 | Number, money and percent formatting; both numeral styles; year grouping; the API-boundary transliteration |
| `jalali.test.ts` | 31 | Conversion, leap years, month grids, a 365-day round trip with no drift, month labels |
| `components.test.tsx` | 32 | UI primitives and the date picker |
| `forms.test.tsx` | 30 | Validation, Persian copy, non-judgemental phrasing |
| `flows.test.tsx` | 15 | Auth gate, dashboard, navigation, quick entry, expired sessions |
| `pages.test.tsx` | 18 | Page-level rendering: dashboard, budgets, debts, assets, reports, insights |
| `a11y.test.tsx` | 9 | Every form control has an accessible name |
| `numerals.test.ts` | 15 | The numeral policy: no locale-dependent formatting in the source, no Persian digit literals outside the conversion tables, and no Persian digit in the rendered output of any route |
| `budget-contract.test.tsx` | 8 | Renders **captured real responses** through the budget and dashboard pages, asserts no fixture invents a key the server does not send, and pins the save request shape |
| `deploy-hygiene.test.ts` | 9 | Source-level checks that protect the deployment contract |

Totals are 212. `budget-contract.test.tsx` is worth knowing about for the same reason as
`numerals.test.ts`. The budget screens once rendered blanks while the whole suite
stayed green, because the fixtures had been written to match the TypeScript type
and the type was wrong. This suite renders responses captured from the running
server instead, and refuses a fixture that declares a key the server never sends.

Both numeral styles are covered deliberately: the default Latin
path, and the Persian path under an explicit `latin: false`, so flipping
`USE_PERSIAN_DIGITS` cannot silently break the product.

`src/test/harness.tsx` is the shared harness. It installs a stub as a **custom
axios adapter** so the real interceptor chain runs. Two details it must get
right, both documented in the file:

1. A custom adapter bypasses axios's `settle`, so it has to honour
   `validateStatus` and throw a real `AxiosError` itself — otherwise every 4xx
   resolves as a success and the error paths go untested.
2. Axios keeps query params in `config.params`, not in `config.url`, so the
   stub folds them in or route matching serves the wrong fixture.

---

## Deployment

The app is built into an nginx image and served from the same origin as the API,
so there is no CORS configuration and the cookie story is identical to
development.

```bash
docker compose up -d --build     # from the repository root
```

Two details of `nginx.conf` are load-bearing:

- **History fallback.** `try_files $uri $uri/ /index.html` — without it a hard
  refresh on `/budgets` returns a 404, because that path exists only in the
  client-side router.
- **`/api` is proxied, not rewritten.** The client's base URL is the relative
  `/api` (`VITE_API_BASE_URL` can override it), which is what makes the same
  build work behind Vite in development and nginx in production.

Caching follows the build output: Vite writes content-hashed filenames
(`assets/index-o4xPhi9R.js`), so those are cached for a year as immutable, while
`index.html` — the file that names them — is served `no-store`. A stale
`index.html` would pin users to the previous deploy.

See [`../DEPLOY.md`](../DEPLOY.md) for the full picture.

---

## Notes

- Recharts is route-split (`React.lazy`) so it stays out of the initial bundle.
- `ReportsPage` and `AssetsPage` load on demand for the same reason.
- Persian weekday names contain **ZWNJ (U+200C)** — `یکشنبه`, `سهشنبه`,
  `پنجشنبه`. Matching on spelled-out names is brittle; prefer a shape regex.
- The transaction list is an **infinite query** (`useTransactions`): «نمایش
  بیشتر» *appends* the next page to what is on screen — the loaded list is
  never replaced. The search input is debounced (300 ms) so typing costs one
  request per pause, not per keystroke.
