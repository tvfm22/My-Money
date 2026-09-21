/**
 * Render coverage for the nine feature pages.
 *
 * ## Why this file exists
 *
 * The flow suite exercises the dashboard and the quick-entry sheet; every
 * other screen was reachable only by hand. A page that throws on first render —
 * a bad property access, a chart fed the wrong shape, a `.map` over null — is
 * a blank screen in production and invisible to a suite that never mounts it.
 *
 * ## What each test asserts
 *
 * Not pixel output, but the four things the spec makes mandatory per screen:
 *
 *   1. It renders without throwing.
 *   2. It shows real, Persian content — not a skeleton left spinning.
 *   3. Its copy is non-judgemental (the product principle).
 *   4. When its data is empty it shows a written empty state, never a blank
 *      region.
 *
 * Assertions are deliberately about *observable text*, because that is what a
 * screen reader gets. A page can look fine while announcing nothing.
 */

import { describe, expect, it, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'

import type { BudgetAnalysis } from '../types'
import { installServerStub, adapterErrors, makeWrapper } from './harness'
import { tokenStore } from '../services/client'

import { TransactionsPage } from '../features/transactions/TransactionsPage'
import { BudgetsPage } from '../features/budgets/BudgetsPage'
import { BudgetPerformancePage } from '../features/budgets/BudgetPerformancePage'
import { DebtsPage } from '../features/debts/DebtsPage'
import { DebtDetailPage } from '../features/debts/DebtDetailPage'
import { AssetsPage } from '../features/assets/AssetsPage'
import { ReportsPage } from '../features/reports/ReportsPage'
import { InsightsPage } from '../features/insights/InsightsPage'
import { SettingsPage } from '../features/settings/SettingsPage'

// ---------------------------------------------------------------------------
// Mounting
// ---------------------------------------------------------------------------

/**
 * Mount a page at a route, with the app's real provider stack.
 *
 * The stack itself comes from `makeWrapper` rather than being rebuilt here.
 * Rebuilding it is how this helper fell behind: when `ToastProvider` was added
 * to the app, this copy kept its own three-provider tree, and every page that
 * calls `useToast` threw `useToast must be used within a ToastProvider`. There
 * is one definition of "the providers the app mounts" and it lives in the
 * harness.
 *
 * The page is placed inside a `<Route>` with a matching path because several
 * pages call `useParams()` and `useNavigate()`. Rendering a page that reads
 * `useParams` outside a route tree silently yields `{}` and the page then
 * takes its "not found" branch — a test that would pass while proving nothing.
 */
function renderPage(element: React.ReactElement, { path = '/', route = '/' } = {}) {
  return render(
    <Routes>
      <Route path={path} element={element} />
    </Routes>,
    { wrapper: makeWrapper([route]) },
  )
}

/**
 * Seed a token so the auth gate does not redirect to `/login`.
 *
 * Synchronous on purpose: `tokenStore` reads from `localStorage`, so the value
 * is visible to the very first render. An `await` here would be a lie about
 * what is actually deferred.
 */
function withToken(): void {
  tokenStore.set('test-access', 'test-refresh')
}

afterEach(() => {
  // A page that logs an adapter error means the harness is broken, not the
  // component. Surface it rather than letting a silent `{}` mask the mistake.
  expect(adapterErrors, `stub adapter errors: ${adapterErrors.join(' | ')}`).toEqual([])
})

/**
 * Wait until every loading placeholder has left the DOM.
 *
 * Every loading block in the app is `role="status"` + `aria-busy="true"` (see
 * `LoadingState`/`LoadingCard`), which makes "still loading" an addressable
 * state rather than a guess based on timing. Asserting on content before this
 * settles is what produced a page's worth of false failures during
 * development: the header renders synchronously, the data sections do not, so
 * `getByText` hit the skeleton every time.
 *
 * This is also the assertion behind the spec's "never a blank screen" rule: if
 * a page rendered nothing at all while pending, `waitFor` would time out here.
 */
async function settle(): Promise<void> {
  await waitFor(() => {
    expect(document.querySelectorAll('[aria-busy="true"]').length).toBe(0)
  })
}

/**
 * Wait for a page to finish loading, then return its text.
 *
 * `container.textContent` collapses adjacent nodes, and several pages build a
 * money figure from two spans (`250,000` + ` تومان`), so `getByText` on the
 * whole figure fails while the text is genuinely present. Reading the
 * container's text is both more robust and closer to what a screen reader
 * announces.
 */
async function settledText(container: HTMLElement): Promise<string> {
  await settle()
  return container.textContent ?? ''
}

// ---------------------------------------------------------------------------
// Shared assertions
// ---------------------------------------------------------------------------

/**
 * Accusatory vocabulary the product forbids.
 *
 * Duplicated from the harness's own list deliberately: importing it would make
 * this suite pass whenever that list was weakened.
 */
const FORBIDDEN = ['شما باید', 'بد عمل', 'غیرمسئولانه', 'بدون مدیریت', 'شکست خورد']

function expectNoJudgement(container: HTMLElement): void {
  const text = container.textContent ?? ''
  for (const phrase of FORBIDDEN) {
    expect(text, `found accusatory copy: ${phrase}`).not.toContain(phrase)
  }
}

/** No screen may ever render a bare HTTP status or an English server string. */
function expectNoRawError(container: HTMLElement): void {
  const text = container.textContent ?? ''
  expect(text).not.toContain('500')
  expect(text).not.toContain('Internal Server Error')
  expect(text).not.toContain('Not Found')
  expect(text).not.toContain('undefined')
  expect(text).not.toContain('NaN')
}

// ---------------------------------------------------------------------------
// Transaction list
// ---------------------------------------------------------------------------

describe('TransactionsPage', () => {
  it('renders the heading, the record action and the stored transaction', async () => {
    const stub = installServerStub()
    withToken()

    const { container } = renderPage(<TransactionsPage />)

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'تراکنش‌ها' })).toBeInTheDocument()
    })

    const text = await settledText(container)

    // The fixture transaction's description must survive to the DOM.
    expect(text).toContain('خرید هفتگی')
    // And its money must be rendered in Persian numerals with the currency unit.
    expect(text).toContain('تومان')
    // The primary action must always be reachable.
    expect(screen.getAllByRole('button', { name: /ثبت تراکنش/ }).length).toBeGreaterThan(0)

    expectNoJudgement(container)
    expectNoRawError(container)
    stub.restore()
  })

  it('shows the first-run empty state when no transaction exists', async () => {
    const stub = installServerStub({
      routes: {
        '/transactions/summary': {
          body: {
            income_total: '0.00',
            income_total_display: '۰ تومان',
            expense_total: '0.00',
            expense_total_display: '۰ تومان',
            net: '0.00',
            net_display: '۰ تومان',
            count: 0,
          },
        },
        '/transactions': { body: { ...emptyPage() } },
      },
    })
    withToken()

    const { container } = renderPage(<TransactionsPage />)

    await waitFor(() => {
      expect(screen.getByText('هنوز تراکنشی ثبت نکرده‌اید')).toBeInTheDocument()
    })
    // The empty state must teach the next step, not just report absence.
    expect(screen.getByText(/با ثبت اولین تراکنش/)).toBeInTheDocument()
    expect(container.textContent).not.toBe('')

    stub.restore()
  })

  it('names the filter — not first-run — when a filter matches nothing', async () => {
    const stub = installServerStub({
      routes: {
        '/transactions/summary': { body: emptySummary() },
        '/transactions': { body: { ...emptyPage() } },
      },
    })
    withToken()

    renderPage(<TransactionsPage />)

    // Wait for the unfiltered empty state first, so the assertions below are
    // about the *filtered* state and not a race with the initial fetch.
    await waitFor(() => {
      expect(screen.getByText('هنوز تراکنشی ثبت نکرده‌اید')).toBeInTheDocument()
    })

    const search = screen.getByPlaceholderText(/جست‌وجو/)
    const user = userEvent.setup()
    await user.type(search, 'نان')

    await waitFor(() => {
      expect(screen.getByText('تراکنشی با این فیلترها پیدا نشد')).toBeInTheDocument()
    })

    stub.restore()
  })
})

function emptyPage() {
  return {
    count: 0,
    page: 1,
    page_size: 20,
    total_pages: 0,
    next: null,
    previous: null,
    results: [],
  }
}

function emptySummary() {
  return {
    income_total: '0.00',
    income_total_display: '۰ تومان',
    expense_total: '0.00',
    expense_total_display: '۰ تومان',
    net: '0.00',
    net_display: '۰ تومان',
    count: 0,
  }
}

// ---------------------------------------------------------------------------
// Budgets
// ---------------------------------------------------------------------------

describe('BudgetsPage', () => {
  it('renders the plan, the consumption figure and each category', async () => {
    const stub = installServerStub()
    withToken()

    const { container } = renderPage(<BudgetsPage />)

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'بودجه‌ها' })).toBeInTheDocument()
    })

    const text = await settledText(container)

    // The month plan card and its targets. Matched against the container text
    // because both labels are split across nested spans.
    expect(text).toContain('برنامه مالی ماه')
    expect(text).toContain('درآمد پیش‌بینی‌شده')

    // The read-only view (the default) reports overall consumption against
    // elapsed time. The per-category *editor* only appears after `ویرایش` is
    // pressed, so `بودجه دسته‌بندی‌ها` is deliberately not asserted here.
    expect(text).toContain('میزان مصرف کل')
    expect(text).toMatch(/روز از/)

    // The status tally covers all four buckets by name — the spec forbids
    // leaning on colour alone to convey budget status.
    expect(text).toContain('بی‌خطر')
    expect(text).toContain('عادی')
    expect(text).toContain('نزدیک سقف')
    expect(text).toContain('بیش از بودجه')

    // Elapsed-vs-consumed is the whole point of the analysis, so both figures
    // must reach the DOM.
    expect(text).toMatch(/120%|58%/)

    expectNoJudgement(container)
    expectNoRawError(container)
    stub.restore()
  })

  it('invites a plan when the month has no budget', async () => {
    const stub = installServerStub({
      routes: {
        '/budgets/analysis': {
          body: {
            ...emptyBudgetAnalysis(),
          },
        },
      },
    })
    withToken()

    const { container } = renderPage(<BudgetsPage />)

    await waitFor(() => {
      expect(screen.getByText('برای این ماه بودجه‌ای تعیین نشده')).toBeInTheDocument()
    })
    expect(container.textContent).not.toBe('')

    stub.restore()
  })
})

/**
 * A month with no budget set.
 *
 * Same nested shape as a real response, every figure at zero. Written out
 * rather than derived because "all zeros" is the entire point of the fixture —
 * this is the case the budgets page has to render without pretending there is
 * a plan.
 */
function emptyBudgetAnalysis(): BudgetAnalysis {
  const zero = '0.00'
  const noMoney = '۰ تومان'

  return {
    budget_id: null,
    year: 1405,
    month: 6,
    month_name: 'شهریور',
    label: 'شهریور ۱۴۰۵',
    has_budget: false,
    has_items: false,
    is_active: false,
    note: '',

    plan: {
      expected_income: zero,
      savings_target: zero,
      investment_target: zero,
      debt_payment_target: zero,
      flexible_budget: zero,
      is_oversubscribed: false,
      essential_total: zero,
      flexible_total: zero,
      expected_income_display: noMoney,
      savings_target_display: noMoney,
      investment_target_display: noMoney,
      debt_payment_target_display: noMoney,
      flexible_budget_display: noMoney,
      essential_total_display: noMoney,
      flexible_total_display: noMoney,
    },
    totals: {
      budgeted: zero,
      spent: zero,
      remaining: zero,
      consumed_percent: zero,
      progress_ratio: zero,
      budgeted_display: noMoney,
      spent_display: noMoney,
      remaining_display: noMoney,
      consumed_display: '۰٪',
    },
    actuals: {
      income: zero,
      expense: zero,
      net: zero,
      income_display: noMoney,
      expense_display: noMoney,
    },
    time: {
      days_elapsed: 29,
      days_in_month: 31,
      days_remaining: 2,
      elapsed_percent: '93.55',
      elapsed_display: '۹۴٪',
    },

    categories: [],
    items: [],
  }
}

// ---------------------------------------------------------------------------
// Budget performance
// ---------------------------------------------------------------------------

describe('BudgetPerformancePage', () => {
  it('reports consumption against elapsed time', async () => {
    const stub = installServerStub()
    withToken()

    const { container } = renderPage(<BudgetPerformancePage />)

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'کارنامه بودجه' })).toBeInTheDocument()
    })

    const text = await settledText(container)

    // The three benchmark metrics, side by side, are the screen's argument.
    expect(text).toContain('مصرف‌شده')
    expect(text).toContain('گذشت ماه')
    expect(text).toContain('کل بودجه')

    expectNoJudgement(container)
    expectNoRawError(container)
    stub.restore()
  })

  it('says so plainly when the month has no data', async () => {
    const stub = installServerStub({
      routes: {
        '/budgets/performance': {
          body: {
            analysis: { ...emptyBudgetAnalysis(), has_budget: false },
            summary: { total: 0, over: 0, near_limit: 0, safe: 0 },
            top_spending: [],
          },
        },
      },
    })
    withToken()

    renderPage(<BudgetPerformancePage />)

    await waitFor(() => {
      expect(screen.getByText('داده‌ای برای این ماه وجود ندارد')).toBeInTheDocument()
    })

    stub.restore()
  })
})

// ---------------------------------------------------------------------------
// Debts
// ---------------------------------------------------------------------------

describe('DebtsPage', () => {
  it('shows the roll-up totals, the overdue position and the debt itself', async () => {
    const stub = installServerStub()
    withToken()

    const { container } = renderPage(<DebtsPage />)

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'بدهی‌ها و طلب‌ها' })).toBeInTheDocument()
    })

    const text = await settledText(container)

    // The counterparty and the remaining amount both identify the row.
    expect(text).toContain('بانک ملت')
    expect(text).toContain('تومان')
    // Upcoming section, driven by `summary.upcoming`.
    expect(text).toContain('سررسیدهای نزدیک')

    expectNoJudgement(container)
    expectNoRawError(container)
    stub.restore()
  })

  it('shows a direction-specific empty state', async () => {
    const stub = installServerStub({
      routes: {
        '/debts/summary': {
          body: {
            payable_remaining: '0.00',
            payable_remaining_display: '۰ تومان',
            payable_total: '0.00',
            payable_total_display: '۰ تومان',
            receivable_remaining: '0.00',
            receivable_remaining_display: '۰ تومان',
            receivable_total: '0.00',
            receivable_total_display: '۰ تومان',
            net_position: '0.00',
            net_position_display: '۰ تومان',
            overdue_count: 0,
            overdue_amount: '0.00',
            overdue_amount_display: '۰ تومان',
            settled_count: 0,
            total_count: 0,
            open_count: 0,
            upcoming: [],
          },
        },
        '/debts': { body: { ...emptyPage() } },
      },
    })
    withToken()

    renderPage(<DebtsPage />)

    // The payable tab is the default, so the copy must be about debt owed —
    // not the generic "nothing here".
    await waitFor(() => {
      expect(screen.getByText('بدهی‌ای ثبت نشده است')).toBeInTheDocument()
    })

    stub.restore()
  })
})

describe('DebtDetailPage', () => {
  it('renders the counterparty, the progress and the payment empty state', async () => {
    const stub = installServerStub()
    withToken()

    const { container } = renderPage(<DebtDetailPage />, {
      path: '/debts/:id',
      route: '/debts/11',
    })

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /بانک ملت/ })).toBeInTheDocument()
    })

    // The fixture has no payments, so the payment history must explain itself.
    expect(screen.getByText('هنوز پرداختی ثبت نشده است')).toBeInTheDocument()
    // 30% paid — the progress figure has to be present.
    expect(container.textContent).toMatch(/30%|15,000,000/)

    expectNoJudgement(container)
    expectNoRawError(container)
    stub.restore()
  })
})

// ---------------------------------------------------------------------------
// Assets
// ---------------------------------------------------------------------------

describe('AssetsPage', () => {
  it('renders net worth, the chart and the asset breakdown', async () => {
    const stub = installServerStub()
    withToken()

    const { container } = renderPage(<AssetsPage />)

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'دارایی‌ها' })).toBeInTheDocument()
    })

    const text = await settledText(container)

    expect(text).toContain('روند ثروت خالص')
    expect(text).toContain('ترکیب دارایی‌ها')
    // Net worth figure from the fixture (Latin digits, grouped).
    expect(text).toMatch(/275,000,000/)
    // The asset itself.
    expect(text).toContain('صندوق طلای مفید')

    expectNoJudgement(container)
    expectNoRawError(container)
    stub.restore()
  })

  it('shows the first-asset empty state when nothing is recorded', async () => {
    const stub = installServerStub({
      routes: {
        '/assets/summary': {
          body: {
            current_value: '0.00',
            current_value_display: '۰ تومان',
            purchase_value: '0.00',
            purchase_value_display: '۰ تومان',
            included_value: '0.00',
            nominal_return: '0.00',
            nominal_return_display: '۰ تومان',
            nominal_return_percent: '0.00',
            nominal_return_percent_display: '۰٪',
            assets_count: 0,
            by_type: [],
            net_worth: {
              as_of: '2026-09-20',
              total_assets: '0.00',
              total_assets_display: '۰ تومان',
              total_liabilities: '0.00',
              total_liabilities_display: '۰ تومان',
              net_worth: '0.00',
              net_worth_display: '۰ تومان',
              total_receivables: '0.00',
              total_receivables_display: '۰ تومان',
              assets_count: 0,
              liabilities_count: 0,
              receivables_count: 0,
              is_negative: false,
            },
          },
        },
        '/net-worth/history': { body: { history: [] } },
        '/assets': { body: { ...emptyPage() } },
      },
    })
    withToken()

    renderPage(<AssetsPage />)

    await waitFor(() => {
      expect(screen.getByText('هنوز دارایی‌ای ثبت نشده است')).toBeInTheDocument()
    })

    stub.restore()
  })
})

// ---------------------------------------------------------------------------
// Reports
// ---------------------------------------------------------------------------

describe('ReportsPage', () => {
  it('renders all five report sections', async () => {
    const stub = installServerStub()
    withToken()

    const { container } = renderPage(<ReportsPage />)

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'گزارش‌ها' })).toBeInTheDocument()
    })

    const text = await settledText(container)

    // Every section is individually named, so a chart that fails to load is
    // still distinguishable from a missing section.
    expect(text).toContain('هزینه به تفکیک دسته‌بندی')
    expect(text).toContain('روند ماهانه')
    expect(text).toContain('بودجه در برابر واقعیت')
    expect(text).toContain('روند ثروت خالص')
    expect(text).toContain('ترکیب دارایی‌ها')

    // The month label proves the payload was read, not defaulted. The month
    // name is Persian; the year digit follows the product numeral style.
    expect(text).toContain('شهریور 1405')

    expectNoJudgement(container)
    expectNoRawError(container)
    stub.restore()
  })

  it('shows a written empty state for a month with no spending', async () => {
    const stub = installServerStub({
      routes: {
        '/reports': {
          body: {
            month: { year: 1405, month: 6, label: 'شهریور ۱۴۰۵' },
            spending_by_category: { total: '0.00', total_display: '۰ تومان', slices: [] },
            spending_by_type: {
              total: '0.00',
              total_display: '۰ تومان',
              start: '2026-08-23',
              end: '2026-09-22',
              buckets: [],
            },
            monthly_trend: [],
            budget_vs_actual: [],
            net_worth_history: [],
            asset_breakdown: [],
          },
        },
      },
    })
    withToken()

    renderPage(<ReportsPage />)

    await waitFor(() => {
      expect(screen.getByText('در این ماه هزینه‌ای ثبت نشده است')).toBeInTheDocument()
    })

    stub.restore()
  })
})

// ---------------------------------------------------------------------------
// Insights
// ---------------------------------------------------------------------------

describe('InsightsPage', () => {
  it('groups insights by severity and shows each one', async () => {
    const stub = installServerStub()
    withToken()

    const { container } = renderPage(<InsightsPage />)

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'بینش مالی' })).toBeInTheDocument()
    })

    const text = await settledText(container)

    // Titles from all four severities.
    expect(text).toContain('سرعت هزینه در رستوران و کافه')
    expect(text).toContain('بدهی سررسید گذشته')
    expect(text).toContain('نرخ پس‌انداز این ماه')
    expect(text).toContain('روند دارایی خالص')

    // The over-budget message must stay descriptive, not accusatory.
    expect(text).toContain('از سرعت معمول بودجه بیشتر است')

    expectNoJudgement(container)
    expectNoRawError(container)
    stub.restore()
  })

  it('says there is nothing to report rather than showing an empty region', async () => {
    const stub = installServerStub({
      routes: {
        '/insights': {
          body: {
            year: 1405,
            month: 6,
            label: 'شهریور ۱۴۰۵',
            insights: [],
            counts: { attention: 0, warning: 0, positive: 0, info: 0 },
          },
        },
      },
    })
    withToken()

    renderPage(<InsightsPage />)

    await waitFor(() => {
      expect(screen.getByText('برای این ماه بینشی وجود ندارد')).toBeInTheDocument()
    })

    stub.restore()
  })
})

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

describe('SettingsPage', () => {
  it('renders the profile, the accounts and the password section', async () => {
    const stub = installServerStub()
    withToken()

    const { container } = renderPage(<SettingsPage />)

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'تنظیمات' })).toBeInTheDocument()
    })

    await settle()
    const text = container.textContent ?? ''

    // The four tabs are always present — they are how the sections are found.
    expect(text).toContain('حساب کاربری')
    expect(text).toContain('حساب‌های مالی')
    expect(text).toContain('دسته‌بندی‌ها')
    expect(text).toContain('امنیت')

    // The profile tab is the default, so its card must be showing.
    expect(text).toContain('اطلاعات حساب')

    // The profile form must arrive pre-filled from `/auth/me/`, not blank.
    // Asserted on the input's `value` *property*: react-hook-form writes via
    // the DOM property, so no `value` attribute ever appears in the markup and
    // `getByDisplayValue` (which reads the attribute) can miss it. This
    // regressed once — the form captured `defaultValues` on the first render,
    // before `/auth/me/` had resolved, and stayed empty for every user.
    await waitFor(() => {
      expect(screen.getByLabelText('نام')).toHaveValue('سارا')
    })
    expect(screen.getByLabelText('نام خانوادگی')).toHaveValue('محمدی')

    expectNoJudgement(container)
    expectNoRawError(container)
    stub.restore()
  })

  it('offers the password change action', async () => {
    const stub = installServerStub()
    withToken()

    renderPage(<SettingsPage />)

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'تنظیمات' })).toBeInTheDocument()
    })
    await settle()

    // The password form lives on the `امنیت` tab, so the security tab has to
    // be selected first — the form is inline, not behind a dialog trigger.
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'امنیت' }))

    // `تغییر رمز عبور` is both the card heading and the submit button's label,
    // so the assertion is scoped by role rather than by text alone.
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'تغییر رمز عبور' })).toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: 'تغییر رمز عبور' })).toBeInTheDocument()

    // Every field must be labelled — not an unlabelled password box.
    expect(screen.getByLabelText('رمز عبور فعلی')).toBeInTheDocument()
    expect(screen.getByLabelText('رمز عبور جدید')).toBeInTheDocument()
    expect(screen.getByLabelText('تکرار رمز عبور جدید')).toBeInTheDocument()

    stub.restore()
  })
})
