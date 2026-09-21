/**
 * Contract tests for the budget payload.
 *
 * ## The failure these exist to prevent
 *
 * The client declared the budget analysis **flat** — `expected_income`,
 * `total_spent_display`, `days_remaining` at the top level — while the server
 * sends it **nested** under `plan`, `totals`, `actuals` and `time`. Because
 * `api.ts` casts with an unchecked `http.get<T>`, TypeScript was satisfied by a
 * shape that does not exist, every one of those reads evaluated to `undefined`,
 * and the budgets page and the dashboard's budget card rendered blanks and
 * zeros.
 *
 * The suite stayed green throughout, and that is the part worth remembering:
 * the fixtures had been written to match the *type*, the type was wrong, and
 * nothing ever compared either of them against the server. A test that asserts
 * against a fixture you wrote yourself cannot catch a contract mismatch — it
 * can only confirm that your assumption is self-consistent.
 *
 * ## The two guards
 *
 * 1. **Rendered against a real response.** `fixtures/budget-analysis.json` and
 *    `fixtures/dashboard.json` are responses captured from the running server,
 *    copied in verbatim. If the client reads a path the server does not send,
 *    the page renders an empty figure and these tests fail.
 *
 * 2. **No invented keys.** The hand-written harness fixtures are checked to
 *    contain only keys the real response also contains. A fixture may hold
 *    different *values* — it needs to be readable and controllable — but it may
 *    not invent a *field*, because that is how the wrong type stayed plausible.
 *
 * Re-capture the JSON fixtures with:
 *
 *     curl -s "http://127.0.0.1:8000/api/budgets/analysis/?year=1405&month=6" \
 *       -H "Authorization: Bearer $TOKEN" > src/test/fixtures/budget-analysis.json
 *
 * They are a snapshot, not a live dependency: if the server contract changes,
 * these tests should be updated deliberately, with the diff reviewed.
 */

import { describe, expect, it } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'

import { BudgetsPage } from '../features/budgets/BudgetsPage'
import { DashboardPage } from '../features/dashboard/DashboardPage'
import { tokenStore } from '../services/client'
import { BUDGET_ANALYSIS, DASHBOARD, installServerStub, makeWrapper } from './harness'

import REAL_ANALYSIS from './fixtures/budget-analysis.json'
import REAL_DASHBOARD from './fixtures/dashboard.json'

/** Seed a token so the auth gate does not redirect. Synchronous by design —
 *  `tokenStore` reads from localStorage and must be visible to the first render. */
function withToken() {
  tokenStore.set('test-access-token', 'test-refresh-token')
}

function renderPage(element: React.ReactElement) {
  return render(
    <Routes>
      <Route path="/" element={element} />
    </Routes>,
    { wrapper: makeWrapper(['/']) },
  )
}

/**
 * Every key path in an object, as `parent.child` strings.
 *
 * Depth-limited because the payload is a few levels deep and a fixture only has
 * to agree about the levels the client actually reads.
 */
function keyPaths(value: unknown, depth = 0, prefix = ''): Set<string> {
  const out = new Set<string>()
  if (depth > 3 || value === null || typeof value !== 'object') return out

  if (Array.isArray(value)) {
    if (value.length > 0) {
      for (const nested of keyPaths(value[0], depth + 1, prefix)) out.add(nested)
    }
    return out
  }

  for (const [key, nested] of Object.entries(value as Record<string, unknown>)) {
    const path = prefix ? `${prefix}.${key}` : key
    out.add(path)
    for (const deeper of keyPaths(nested, depth + 1, path)) out.add(deeper)
  }
  return out
}

// ---------------------------------------------------------------------------
// 1. The real response, rendered
// ---------------------------------------------------------------------------

describe('budget payload contract — rendered against a real response', () => {
  it('renders the figures the server actually sent', async () => {
    installServerStub({ routes: { '/budgets/analysis': { body: REAL_ANALYSIS } } })
    withToken()

    const { container } = renderPage(<BudgetsPage />)

    // Two waits, for two different reasons. The heading proves the page shell
    // mounted; `render()` returns before React's first commit, so an immediate
    // query would resolve against an almost-empty document. Then the figure
    // itself, which only appears once the query resolves.
    await screen.findByRole('heading', { name: 'بودجه‌ها' })

    // The real response's `totals.spent_display` is `۴۳٬۵۲۰٬۰۰۰ تومان` and
    // `totals.budgeted_display` is `۴۹٬۸۰۰٬۰۰۰ تومان`. The response interceptor
    // transliterates both on the way in, so the page shows Latin digits.
    await waitFor(() => {
      expect(container.textContent, 'totals.spent_display did not render').toMatch(/43,520,000/)
    })
    expect(container.textContent, 'totals.budgeted_display did not render').toMatch(/49,800,000/)

    // A wrong read path yields undefined, which is exactly what used to happen.
    expect(container.textContent).not.toContain('undefined')
    expect(container.textContent).not.toContain('NaN')
  })

  it('renders the plan figures, which live one level deeper', async () => {
    installServerStub({ routes: { '/budgets/analysis': { body: REAL_ANALYSIS } } })
    withToken()

    const { container } = renderPage(<BudgetsPage />)
    await screen.findByRole('heading', { name: 'بودجه‌ها' })

    // `expected_income` sits under `plan`, not at the top level. This is the
    // read that returned undefined and left the summary row empty. It renders
    // through `MoneyDisplay compact`, so the label is the scaled form.
    await waitFor(() => {
      expect(container.textContent).toMatch(/48 میلیون/)
    })
  })

  it('does not show the essential/flexible split any more', async () => {
    installServerStub({ routes: { '/budgets/analysis': { body: REAL_ANALYSIS } } })
    withToken()

    const { container } = renderPage(<BudgetsPage />)
    await screen.findByRole('heading', { name: 'بودجه‌ها' })
    await waitFor(() => {
      expect(container.textContent).toMatch(/43,520,000/)
    })

    // The payload still carries `plan.essential_total` and `plan.flexible_total`
    // — the server keeps the flag — but the page no longer presents that split.
    // It duplicated the dashboard's own essential/flexible breakdown with a
    // different source, so the same word meant two different numbers on two
    // screens. Removed from here; the dashboard's version, which comes from each
    // expense's own type, is the one that stayed.
    const text = container.textContent ?? ''
    expect(text, 'the removed split is still rendered').not.toContain('ترکیب بودجه')
    expect(text, 'the removed split is still rendered').not.toContain('هزینه‌های ضروری')
    expect(text, 'the removed split is still rendered').not.toContain('هزینه‌های انعطاف‌پذیر')
  })

  it('renders the dashboard budget card from a real response', async () => {
    installServerStub({ routes: { '/dashboard': { body: REAL_DASHBOARD } } })
    withToken()

    const { container } = renderPage(<DashboardPage />)
    await screen.findByText('مانده قابل خرج')

    // `budget.totals.spent_display`, one level deeper than the flat type
    // claimed. Reading the wrong path left this card blank.
    await waitFor(() => {
      expect(container.textContent).toMatch(/43,520,000/)
    })
    expect(container.textContent).not.toContain('undefined')
  })
})

// ---------------------------------------------------------------------------
// 2. The hand-written fixtures may not invent keys
// ---------------------------------------------------------------------------

describe('budget payload contract — fixtures agree with the server', () => {
  it('the analysis fixture declares no key the server does not send', () => {
    const real = keyPaths(REAL_ANALYSIS)
    const invented = [...keyPaths(BUDGET_ANALYSIS)].filter((p) => !real.has(p))

    expect(invented, `fixture declares keys the server never sends: ${invented.join(', ')}`).toEqual([])
  })

  it('the analysis fixture carries every nested block the server sends', () => {
    const fixture = keyPaths(BUDGET_ANALYSIS)
    for (const block of ['plan', 'totals', 'actuals', 'time']) {
      expect(fixture, `fixture is missing the \`${block}\` block`).toContain(block)
    }
  })

  it('the dashboard fixture declares no key the server does not send', () => {
    const real = keyPaths(REAL_DASHBOARD)
    const invented = [...keyPaths(DASHBOARD)].filter((p) => !real.has(p))

    expect(invented, `fixture declares keys the server never sends: ${invented.join(', ')}`).toEqual([])
  })

  it('the flat field names that caused this bug are gone from the type', () => {
    // A regression guard with teeth: these are the exact paths the client used
    // to read. If any reappears, the screens go blank again.
    const real = keyPaths(REAL_ANALYSIS)
    for (const wrong of [
      'expected_income',
      'total_budgeted_display',
      'total_spent_display',
      'total_remaining_display',
      'total_consumed_percent',
      'actual_income',
      'actual_expense',
      'days_remaining',
      'elapsed_percent',
    ]) {
      expect(real, `\`${wrong}\` must not exist at the top level of the payload`).not.toContain(wrong)
    }
  })
})

// ---------------------------------------------------------------------------
// 3. Saving a plan uses the key the server actually reads
// ---------------------------------------------------------------------------

describe('budget payload contract — saving a plan', () => {
  it('sends `allocations`, and never `items` or a line classification', async () => {
    // The captured month is genuinely oversubscribed, and the form correctly
    // refuses to save in that state — so this test raises the income envelope
    // to make the save reachable. Everything else is the real response.
    const saveable = {
      ...REAL_ANALYSIS,
      plan: {
        ...REAL_ANALYSIS.plan,
        expected_income: '900000000.00',
        is_oversubscribed: false,
      },
    }

    // The category picker lists the same categories the budget is built from —
    // in the app they are one set, and the edit form seeds each row's amount by
    // category id. The default harness picker uses different ids, so a test that
    // relies on it opens the form with every amount blank and cannot save.
    const picker = REAL_ANALYSIS.categories.map((category) => ({
      id: category.category_id,
      name: category.category_name,
      kind: 'expense' as const,
      icon: category.category_icon,
      color: category.category_color,
      parent: null,
    }))

    const stub = installServerStub({
      routes: {
        '/budgets/analysis': { body: saveable },
        '/budgets/plan': { body: { budget: null, analysis: saveable } },
        '/categories/picker': { body: picker },
      },
    })
    withToken()
    const user = userEvent.setup()

    renderPage(<BudgetsPage />)
    await screen.findByRole('heading', { name: 'بودجه‌ها' })

    // Enter edit mode and wait for the rows to be seeded from the response.
    await user.click(await screen.findByRole('button', { name: 'ویرایش' }))

    await user.click(screen.getByRole('button', { name: /ذخیره/ }))

    await waitFor(() => {
      expect(stub.writes.length).toBeGreaterThan(0)
    })

    const body = stub.writes[0].body as Record<string, unknown>

    // The bug: this used to be `items`, which DRF silently dropped, so saving
    // returned 200 and changed nothing.
    expect(body, 'the request must use the server\'s key').not.toHaveProperty('items')
    expect(body).toHaveProperty('allocations')

    const allocations = body.allocations as Array<Record<string, unknown>>
    expect(Array.isArray(allocations)).toBe(true)
    expect(allocations.length).toBeGreaterThan(0)
    expect(allocations[0]).toHaveProperty('category')
    expect(allocations[0]).toHaveProperty('amount')

    // The budget page no longer classifies a line as essential or flexible. The
    // server still accepts the flag, but sending it from here would put the
    // interface back in the business of maintaining a split it no longer shows —
    // and an explicit value is not the same as an absent one, so it would start
    // overwriting stored flags again.
    expect(
      allocations.every((entry) => !('is_essential' in entry)),
      'the budget form must not send is_essential any more',
    ).toBe(true)

    // And nothing on the page offers to set it.
    expect(screen.queryAllByRole('switch')).toHaveLength(0)

    stub.restore()
  })
})
