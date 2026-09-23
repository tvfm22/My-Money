/**
 * Test harness for component and flow tests.
 *
 * ## Why a custom adapter
 *
 * `client.ts` builds an axios instance whose default adapter is XHR. jsdom's
 * XHR is a stub that never resolves, and — unlike a real browser — it cannot be
 * redirected at `fetch`. Axios *does* accept a plain function as its adapter,
 * and that function is called directly with the resolved config, so stubbing at
 * that level gives us a precise, synchronous-enough seam with no network, no
 * timers waiting on a dead socket, and full access to the request body.
 *
 * The alternative (`adapter: 'fetch'` plus a `fetch` stub) was tried and does
 * not work here: axios resolves the named adapter through its own registry
 * before consulting `globalThis.fetch`, so the stub is never reached.
 */

import { vi } from 'vitest'
import { AxiosError } from 'axios'
import type { ReactNode } from 'react'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import App from '../App'

import type {
  AssetSummary,
  BudgetActuals,
  BudgetAnalysis,
  BudgetCategoryAnalysis,
  BudgetPlan,
  BudgetStatus,
  BudgetTime,
  BudgetTotals,
  CategoryPickerItem,
  Dashboard,
  DebtSummary,
  InsightsResponse,
  NetWorth,
  NetWorthPoint,
  PaceStatus,
  ReportsPayload,
} from '../types'
import { AuthProvider } from '../hooks/useAuth'
import { ThemeProvider } from '../hooks/useTheme'
import { ToastProvider } from '../components/ui/Toast'
import { http } from '../services/client'
import { formatMoney, formatPercent } from '../utils/format'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

export const CATEGORIES_EXPENSE: CategoryPickerItem[] = [
  { id: 1, name: 'خوراک', kind: 'expense', icon: 'utensils', color: '#e08c00', parent: null },
  { id: 2, name: 'حمل‌ونقل', kind: 'expense', icon: 'bus', color: '#3566e8', parent: null },
]

export const CATEGORIES_INCOME: CategoryPickerItem[] = [
  { id: 10, name: 'حقوق', kind: 'income', icon: 'wallet', color: '#12a150', parent: null },
]

export const ACCOUNT = {
  id: 5,
  name: 'بانک ملت',
  account_type: 'bank',
  account_type_label: 'حساب بانکی',
  opening_balance: '0.00',
  opening_balance_display: '۰ تومان',
  current_balance: '1200000.00',
  current_balance_display: '۱٬۲۰۰٬۰۰۰ تومان',
  income_total: '5000000.00',
  income_total_display: '۵٬۰۰۰٬۰۰۰ تومان',
  expense_total: '3800000.00',
  expense_total_display: '۳٬۸۰۰٬۰۰۰ تومان',
  color: '#3566e8',
  icon: 'banknote',
  institution: 'ملت',
  include_in_total: true,
  is_active: true,
  sort_order: 0,
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-01T00:00:00Z',
}

export const ACCOUNTS_PAGE = {
  count: 1,
  page: 1,
  page_size: 100,
  total_pages: 1,
  next: null,
  previous: null,
  results: [ACCOUNT],
}

export const ASSET = {
  id: 3,
  name: 'صندوق طلای مفید',
  asset_type: 'gold_fund',
  asset_type_label: 'صندوق طلا',
  current_value: '150000000.00',
  current_value_display: '۱۵۰٬۰۰۰٬۰۰۰ تومان',
  purchase_value: '120000000.00',
  purchase_value_display: '۱۲۰٬۰۰۰٬۰۰۰ تومان',
  nominal_return: '30000000.00',
  nominal_return_display: '۳۰٬۰۰۰٬۰۰۰ تومان',
  nominal_return_percent: '25.00',
  nominal_return_percent_display: '۲۵٪',
  is_profitable: true,
  total_cost_display: '۱۲۰٬۰۰۰٬۰۰۰ تومان',
  quantity: '125.000',
  unit: 'واحد',
  unit_price: '1200000.00',
  purchase_date: '2026-05-01',
  purchase_date_display: '۱۱ اردیبهشت ۱۴۰۵',
  last_valued_on: null,
  description: '',
  note: '',
  provider: 'مفید',
  account: null,
  owner_name: 'سارا محمدی',
  include_in_net_worth: true,
  is_active: true,
  created_at: '2026-05-01T00:00:00Z',
  updated_at: '2026-05-01T00:00:00Z',
}

export const TRANSACTION = {
  id: 7,
  transaction_type: 'expense' as const,
  transaction_type_label: 'هزینه',
  amount: '250000.00',
  amount_display: '۲۵۰٬۰۰۰ تومان',
  signed_amount: '-250000.00',
  category: 1,
  category_detail: CATEGORIES_EXPENSE[0],
  account: null,
  account_name: null,
  account_icon: null,
  occurred_on: '2026-09-20',
  jalali_date: '1405/06/29',
  date_display: '۲۹ شهریور ۱۴۰۵',
  date_short: '۲۹ شهریور',
  spending_type: 'flexible' as const,
  spending_type_label: 'انعطاف‌پذیر',
  description: 'خرید هفتگی',
  title: 'خرید هفتگی',
  note: '',
  tags: [],
  created_at: '2026-09-20T00:00:00Z',
  updated_at: '2026-09-20T00:00:00Z',
}

export const DEBT = {
  id: 11,
  direction: 'payable' as const,
  direction_label: 'بدهی',
  counterparty: 'بانک ملت',
  principal: '50000000.00',
  principal_display: '۵۰٬۰۰۰٬۰۰۰ تومان',
  paid_amount: '15000000.00',
  paid_display: '۱۵٬۰۰۰٬۰۰۰ تومان',
  remaining_amount: '35000000.00',
  remaining_display: '۳۵٬۰۰۰٬۰۰۰ تومان',
  paid_percent: '30.00',
  paid_percent_display: '۳۰٪',
  status: 'partial' as const,
  status_label: 'بخشی پرداخت شده',
  is_overdue: false,
  is_settled: false,
  days_until_due: 12,
  due_relative: '۱۲ روز مانده',
  issued_on: '2026-07-01',
  issued_on_display: '۱۰ تیر ۱۴۰۵',
  due_on: '2026-10-02',
  due_on_display: '۱۰ مهر ۱۴۰۵',
  description: 'وام خرید خودرو',
  note: '',
  account: null,
  account_name: null,
  payments: [],
  payments_count: 0,
  created_at: '2026-07-01T00:00:00Z',
  updated_at: '2026-07-01T00:00:00Z',
}

// ---------------------------------------------------------------------------
// Budget analysis
//
// The *shape* of these fixtures is the most important thing in this file.
//
// The payload is nested — `plan`, `totals`, `actuals`, `time` — and the client
// types used to declare it flat. Because `api.ts` casts with an unchecked
// `http.get<T>`, TypeScript accepted the wrong shape, every read evaluated to
// `undefined`, and the budget screens rendered blanks while the whole suite
// stayed green: the fixtures agreed with the types because both were written
// from the same wrong assumption, and nothing ever compared either against the
// server.
//
// Three rules follow:
//
//   1. These fixtures are built through factories, so every field is present
//      and correctly named by construction. A test states only what it asserts.
//   2. The `_display` strings carry **Persian** digits, because that is what the
//      server actually sends and `numerals.test.ts` depends on it — the response
//      interceptor transliterates them, so a fixture with Latin digits would
//      make that sweep pass trivially instead of proving anything.
//   3. `harness.test.ts` checks this shape against a response captured from the
//      running server. That check is what makes rule 1 enforceable rather than
//      aspirational.
// ---------------------------------------------------------------------------

/** The Jalali month every budget fixture describes. */
const BUDGET_MONTH = { year: 1405, month: 6, name: 'شهریور', label: 'شهریور ۱۴۰۵' }

const DAYS_ELAPSED = 29
const DAYS_IN_MONTH = 31
const ELAPSED_PERCENT = '93.55'

/** Money as the server renders it: Persian digits, U+066C separator. */
const money = (value: string | number) => formatMoney(value, { latin: false })
/** A whole-number percent as the server renders it: `۹۴٪`. */
const pct = (value: string | number) => formatPercent(Number(value), 0, { latin: false })

export interface CategorySpec {
  category_id: number
  category_name: string
  category_icon: string
  category_color: string
  is_essential: boolean
  budgeted: string
  spent: string
  status: BudgetStatus
  status_label: string
  pace_state: PaceStatus
  message: string
}

/**
 * A complete analysed category.
 *
 * The derived figures are computed from `budgeted` and `spent` rather than
 * typed out, so a fixture cannot contradict itself — the previous hand-written
 * version had a category whose `consumed_percent` did not match its own
 * `spent`/`budgeted` pair.
 */
export function categoryAnalysis(spec: CategorySpec): BudgetCategoryAnalysis {
  const budgeted = Number(spec.budgeted)
  const spent = Number(spec.spent)
  const remaining = budgeted - spent
  const consumed = budgeted > 0 ? (spent / budgeted) * 100 : 0
  const over = Math.max(spent - budgeted, 0)
  const projected = DAYS_ELAPSED > 0 ? (spent / DAYS_ELAPSED) * DAYS_IN_MONTH : spent

  return {
    category_id: spec.category_id,
    category_name: spec.category_name,
    category_icon: spec.category_icon,
    category_color: spec.category_color,
    category_full_path: spec.category_name,
    is_essential: spec.is_essential,

    budgeted: spec.budgeted,
    spent: spec.spent,
    remaining: remaining.toFixed(2),
    consumed_percent: consumed.toFixed(2),
    elapsed_percent: ELAPSED_PERCENT,
    pace_delta: (consumed - Number(ELAPSED_PERCENT)).toFixed(2),
    progress_ratio: Math.min(consumed / 100, 1).toFixed(4),

    status: spec.status,
    status_label: spec.status_label,
    pace_state: spec.pace_state,
    message: spec.message,

    projected_total: projected.toFixed(2),
    projected_over_budget: projected > budgeted,
    transaction_count: 7,
    days_elapsed: DAYS_ELAPSED,
    days_in_month: DAYS_IN_MONTH,

    over_budget_amount: over.toFixed(2),

    budgeted_display: money(spec.budgeted),
    spent_display: money(spec.spent),
    remaining_display: money(remaining),
    consumed_display: pct(consumed),
    elapsed_display: pct(ELAPSED_PERCENT),
    over_budget_display: money(over),
    projected_display: money(projected),
  }
}

/** One category within budget, and one that has run over it. */
export const BUDGET_CATEGORY_ANALYSIS: BudgetAnalysis['categories'] = [
  categoryAnalysis({
    category_id: 1,
    category_name: 'خوراک',
    category_icon: 'utensils',
    category_color: '#e08c00',
    is_essential: true,
    budgeted: '10000000.00',
    spent: '4000000.00',
    status: 'safe',
    status_label: 'در محدوده بودجه',
    pace_state: 'behind',
    message: 'هزینه این دسته کمتر از سهم روزهای سپری‌شده از ماه است.',
  }),
  categoryAnalysis({
    category_id: 3,
    category_name: 'رستوران و کافه',
    category_icon: 'coffee',
    category_color: '#d64545',
    is_essential: false,
    budgeted: '3000000.00',
    spent: '3600000.00',
    status: 'over',
    status_label: 'بیشتر از بودجه',
    pace_state: 'ahead',
    message: 'هزینه این دسته از سرعت معمول بودجه بیشتر است.',
  }),
]

const BUDGET_PLAN: BudgetPlan = {
  expected_income: '90000000.00',
  savings_target: '10000000.00',
  investment_target: '5000000.00',
  debt_payment_target: '8000000.00',
  flexible_budget: '67000000.00',
  is_oversubscribed: false,
  essential_total: '10000000.00',
  flexible_total: '3000000.00',

  expected_income_display: money('90000000.00'),
  savings_target_display: money('10000000.00'),
  investment_target_display: money('5000000.00'),
  debt_payment_target_display: money('8000000.00'),
  flexible_budget_display: money('67000000.00'),
  essential_total_display: money('10000000.00'),
  flexible_total_display: money('3000000.00'),
}

const BUDGET_TOTALS: BudgetTotals = {
  budgeted: '13000000.00',
  spent: '7600000.00',
  remaining: '5400000.00',
  consumed_percent: '58.46',
  progress_ratio: '0.5846',

  budgeted_display: money('13000000.00'),
  spent_display: money('7600000.00'),
  remaining_display: money('5400000.00'),
  consumed_display: pct(58),
}

const BUDGET_ACTUALS: BudgetActuals = {
  income: '90000000.00',
  expense: '48000000.00',
  net: '42000000.00',
  income_display: money('90000000.00'),
  expense_display: money('48000000.00'),
}

const BUDGET_TIME: BudgetTime = {
  days_elapsed: DAYS_ELAPSED,
  days_in_month: DAYS_IN_MONTH,
  days_remaining: DAYS_IN_MONTH - DAYS_ELAPSED,
  elapsed_percent: ELAPSED_PERCENT,
  elapsed_display: pct(ELAPSED_PERCENT),
}

export const BUDGET_ANALYSIS: BudgetAnalysis = {
  budget_id: 4,
  year: BUDGET_MONTH.year,
  month: BUDGET_MONTH.month,
  month_name: BUDGET_MONTH.name,
  label: BUDGET_MONTH.label,
  has_budget: true,
  has_items: true,
  is_active: true,
  note: '',

  plan: BUDGET_PLAN,
  totals: BUDGET_TOTALS,
  actuals: BUDGET_ACTUALS,
  time: BUDGET_TIME,

  categories: BUDGET_CATEGORY_ANALYSIS,
  items: [],
}

/**
 * A dashboard payload with a healthy, a warning and an over-budget category.
 *
 * Deliberately includes all three budget statuses so a flow test can assert
 * that the screen distinguishes them by *both* colour and wording — the spec
 * forbids colour as the sole carrier of meaning.
 */
export const DASHBOARD: Dashboard = {
  greeting_name: 'رضا',
  month: {
    year: BUDGET_MONTH.year,
    month: BUDGET_MONTH.month,
    // The dashboard calls the month name `name`; the analysis payload calls it
    // `month_name`. Mirroring the server exactly is the point of this fixture.
    name: BUDGET_MONTH.name,
    label: BUDGET_MONTH.label,
    ...BUDGET_TIME,
  },
  summary: {
    balance: '42000000.00',
    balance_display: '۴۲٬۰۰۰٬۰۰۰ تومان',
    income: '90000000.00',
    income_display: '۹۰٬۰۰۰٬۰۰۰ تومان',
    expense: '48000000.00',
    expense_display: '۴۸٬۰۰۰٬۰۰۰ تومان',
    net: '42000000.00',
    net_display: '۴۲٬۰۰۰٬۰۰۰ تومان',
    spendable: '12500000.00',
    spendable_display: '۱۲٬۵۰۰٬۰۰۰ تومان',
    total_assets: '310000000.00',
    total_assets_display: '۳۱۰٬۰۰۰٬۰۰۰ تومان',
    total_debts: '35000000.00',
    total_debts_display: '۳۵٬۰۰۰٬۰۰۰ تومان',
    total_receivables: '8000000.00',
    total_receivables_display: '۸٬۰۰۰٬۰۰۰ تومان',
    net_worth: '283000000.00',
    net_worth_display: '۲۸۳٬۰۰۰٬۰۰۰ تومان',
    transactions_count: 42,
  },
  comparison: {
    previous_month_label: 'مرداد ۱۴۰۵',
    income: {
      current: '90000000.00',
      previous: '80000000.00',
      delta: '10000000.00',
      percent: '12.50',
      direction: 'up' as const,
      delta_display: money('10000000.00'),
      percent_display: pct(13),
    },
    expense: {
      current: '48000000.00',
      previous: '50100000.00',
      delta: '-2100000.00',
      percent: '-4.19',
      direction: 'down' as const,
      delta_display: money('-2100000.00'),
      percent_display: pct(4),
    },
  },
  // The dashboard's budget card is a subset of a full analysis — same nested
  // `plan` / `totals` blocks, and `top_categories` is the same category shape,
  // which is why the same component renders both.
  budget: {
    has_budget: true,
    label: 'شهریور ۱۴۰۵',
    categories_count: 3,
    plan: BUDGET_PLAN,
    totals: BUDGET_TOTALS,
    top_categories: [
      BUDGET_CATEGORY_ANALYSIS[0],
      categoryAnalysis({
        category_id: 2,
        category_name: 'حمل‌ونقل',
        category_icon: 'bus',
        category_color: '#3566e8',
        is_essential: true,
        budgeted: '5000000.00',
        spent: '3300000.00',
        status: 'near_limit',
        status_label: 'نزدیک به سقف بودجه',
        pace_state: 'on_track',
        message: 'مصرف این دسته نزدیک سقف بودجه است.',
      }),
      BUDGET_CATEGORY_ANALYSIS[1],
    ],
  },
  // How this month's spending splits by the user's own classification. Flat,
  // not nested under `budget`, because it describes the month's expenses
  // rather than the plan.
  spending_types: {
    total: '48000000.00',
    total_display: money('48000000.00'),
    start: '2026-08-23',
    end: '2026-09-22',
    buckets: [
      {
        key: 'essential',
        label: 'ضروری',
        amount: '33600000.00',
        amount_display: money('33600000.00'),
        share_percent: '70.00',
        share_display: pct(70),
        transaction_count: 21,
      },
      {
        key: 'flexible',
        label: 'انعطاف‌پذیر',
        amount: '14400000.00',
        amount_display: money('14400000.00'),
        share_percent: '30.00',
        share_display: pct(30),
        transaction_count: 14,
      },
    ],
  },
  recent_transactions: [TRANSACTION],
  accounts_count: 3,
}

/**
 * The roll-up the debts screen leads with.
 *
 * Mirrors the live payload shape: four money totals, a net position, three
 * counts, and a pre-sorted `upcoming` list. `overdue_count` is non-zero on
 * purpose so the screen's overdue branch is exercised.
 */
export const DEBT_SUMMARY: DebtSummary = {
  payable_remaining: '35000000.00',
  payable_remaining_display: '۳۵٬۰۰۰٬۰۰۰ تومان',
  payable_total: '50000000.00',
  payable_total_display: '۵۰٬۰۰۰٬۰۰۰ تومان',
  receivable_remaining: '8000000.00',
  receivable_remaining_display: '۸٬۰۰۰٬۰۰۰ تومان',
  receivable_total: '8000000.00',
  receivable_total_display: '۸٬۰۰۰٬۰۰۰ تومان',
  net_position: '-27000000.00',
  net_position_display: '۲۷٬۰۰۰٬۰۰۰ تومان بدهکار',
  overdue_count: 1,
  overdue_amount: '2000000.00',
  overdue_amount_display: '۲٬۰۰۰٬۰۰۰ تومان',
  settled_count: 2,
  total_count: 4,
  open_count: 2,
  upcoming: [DEBT],
}

/**
 * The debt-side half of net worth, as the assets screen receives it.
 *
 * `is_negative` is `false` because `net_worth` is positive in this fixture —
 * the flag mirrors the server's own comparison, and a fixture that contradicts
 * it would let a real bug through.
 */
export const NET_WORTH: NetWorth = {
  as_of: '2026-09-20',
  total_assets: '310000000.00',
  total_assets_display: '۳۱۰٬۰۰۰٬۰۰۰ تومان',
  total_liabilities: '35000000.00',
  total_liabilities_display: '۳۵٬۰۰۰٬۰۰۰ تومان',
  net_worth: '275000000.00',
  net_worth_display: '۲۷۵٬۰۰۰٬۰۰۰ تومان',
  total_receivables: '8000000.00',
  total_receivables_display: '۸٬۰۰۰٬۰۰۰ تومان',
  assets_count: 5,
  liabilities_count: 2,
  receivables_count: 2,
  is_negative: false,
}

export const ASSET_SUMMARY: AssetSummary = {
  current_value: '310000000.00',
  current_value_display: '۳۱۰٬۰۰۰٬۰۰۰ تومان',
  purchase_value: '262000000.00',
  purchase_value_display: '۲۶۲٬۰۰۰٬۰۰۰ تومان',
  included_value: '310000000.00',
  nominal_return: '48000000.00',
  nominal_return_display: '۴۸٬۰۰۰٬۰۰۰ تومان',
  nominal_return_percent: '18.32',
  nominal_return_percent_display: '۱۸٪',
  assets_count: 5,
  by_type: [
    { type: 'gold_fund', total: '150000000.00', display: '۱۵۰٬۰۰۰٬۰۰۰ تومان' },
    { type: 'bank_account', total: '90000000.00', display: '۹۰٬۰۰۰٬۰۰۰ تومان' },
    { type: 'stocks', total: '70000000.00', display: '۷۰٬۰۰۰٬۰۰۰ تومان' },
  ],
  net_worth: NET_WORTH,
}

/**
 * Six months of net-worth history.
 *
 * Deliberately includes one negative month: the chart and the delta badge both
 * have a negative branch, and a fixture that only ever rises would never reach
 * it.
 */
export const NET_WORTH_HISTORY: NetWorthPoint[] = [
  { year: 1405, month: 1, key: '1405-01', label: 'فروردین ۱۴۰۵', month_name: 'فروردین', assets: '240000000.00', liabilities: '90000000.00', net_worth: '150000000.00' },
  { year: 1405, month: 2, key: '1405-02', label: 'اردیبهشت ۱۴۰۵', month_name: 'اردیبهشت', assets: '255000000.00', liabilities: '80000000.00', net_worth: '175000000.00' },
  { year: 1405, month: 3, key: '1405-03', label: 'خرداد ۱۴۰۵', month_name: 'خرداد', assets: '262000000.00', liabilities: '72000000.00', net_worth: '190000000.00' },
  { year: 1405, month: 4, key: '1405-04', label: 'تیر ۱۴۰۵', month_name: 'تیر', assets: '278000000.00', liabilities: '60000000.00', net_worth: '218000000.00' },
  { year: 1405, month: 5, key: '1405-05', label: 'مرداد ۱۴۰۵', month_name: 'مرداد', assets: '295000000.00', liabilities: '42000000.00', net_worth: '253000000.00' },
  { year: 1405, month: 6, key: '1405-06', label: 'شهریور ۱۴۰۵', month_name: 'شهریور', assets: '310000000.00', liabilities: '35000000.00', net_worth: '275000000.00' },
]

export const REPORTS: ReportsPayload = {
  month: { year: 1405, month: 6, label: 'شهریور ۱۴۰۵' },
  spending_by_category: {
    total: '48000000.00',
    total_display: '۴۸٬۰۰۰٬۰۰۰ تومان',
    slices: [
      { category_id: 1, category_name: 'خوراک', icon: 'utensils', color: '#e08c00', amount: '18000000.00', amount_display: '۱۸٬۰۰۰٬۰۰۰ تومان', share_percent: '37.50', share_display: '۳۸٪', count: 18 },
      { category_id: 2, category_name: 'حمل‌ونقل', icon: 'bus', color: '#3566e8', amount: '9000000.00', amount_display: '۹٬۰۰۰٬۰۰۰ تومان', share_percent: '18.75', share_display: '۱۹٪', count: 11 },
      { category_id: 3, category_name: 'رستوران و کافه', icon: 'coffee', color: '#d64545', amount: '3600000.00', amount_display: '۳٬۶۰۰٬۰۰۰ تومان', share_percent: '7.50', share_display: '۸٪', count: 7 },
    ],
  },
  monthly_trend: [
    { year: 1405, month: 4, key: '1405-04', label: 'تیر ۱۴۰۵', label_short: 'تیر', income: '82000000.00', expense: '51000000.00', net: '31000000.00' },
    { year: 1405, month: 5, key: '1405-05', label: 'مرداد ۱۴۰۵', label_short: 'مرداد', income: '85000000.00', expense: '46000000.00', net: '39000000.00' },
    { year: 1405, month: 6, key: '1405-06', label: 'شهریور ۱۴۰۵', label_short: 'شهریور', income: '90000000.00', expense: '48000000.00', net: '42000000.00' },
  ],
  // Same shape as the dashboard's `spending_types` — one shared builder on the
  // server produces both.
  spending_by_type: {
    total: '48000000.00',
    total_display: '۴۸٬۰۰۰٬۰۰۰ تومان',
    start: '2026-08-23',
    end: '2026-09-22',
    buckets: [
      {
        key: 'essential',
        label: 'ضروری',
        amount: '33600000.00',
        amount_display: '۳۳٬۶۰۰٬۰۰۰ تومان',
        share_percent: '70.00',
        share_display: '۷۰٪',
        transaction_count: 21,
      },
      {
        key: 'flexible',
        label: 'انعطاف‌پذیر',
        amount: '14400000.00',
        amount_display: '۱۴٬۴۰۰٬۰۰۰ تومان',
        share_percent: '30.00',
        share_display: '۳۰٪',
        transaction_count: 14,
      },
    ],
  },
  budget_vs_actual: [
    { category_id: 1, category_name: 'خوراک', icon: 'utensils', color: '#e08c00', budgeted: '10000000.00', budgeted_display: '۱۰٬۰۰۰٬۰۰۰ تومان', actual: '4000000.00', actual_display: '۴٬۰۰۰٬۰۰۰ تومان', difference: '6000000.00', difference_display: '۶٬۰۰۰٬۰۰۰ تومان باقی‌مانده', status: 'safe', spending_types: { total: '4000000.00', total_display: '۴٬۰۰۰٬۰۰۰ تومان', start: '2026-08-23', end: '2026-09-22', buckets: [ { key: 'essential', label: 'ضروری', amount: '3000000.00', amount_display: '۳٬۰۰۰٬۰۰۰ تومان', share_percent: '75.00', share_display: '۷۵٪', transaction_count: 5 }, { key: 'flexible', label: 'انعطاف‌پذیر', amount: '1000000.00', amount_display: '۱٬۰۰۰٬۰۰۰ تومان', share_percent: '25.00', share_display: '۲۵٪', transaction_count: 2 } ] } },
    { category_id: 3, category_name: 'رستوران و کافه', icon: 'coffee', color: '#d64545', budgeted: '3000000.00', budgeted_display: '۳٬۰۰۰٬۰۰۰ تومان', actual: '3600000.00', actual_display: '۳٬۶۰۰٬۰۰۰ تومان', difference: '-600000.00', difference_display: '۶۰۰٬۰۰۰ تومان بیش از بودجه', status: 'over' },
  ],
  net_worth_history: NET_WORTH_HISTORY,
  asset_breakdown: [
    { type: 'gold_fund', label: 'صندوق طلا', total: '150000000.00', total_display: '۱۵۰٬۰۰۰٬۰۰۰ تومان', share_percent: '48.39' },
    { type: 'bank_account', label: 'حساب بانکی', total: '90000000.00', total_display: '۹۰٬۰۰۰٬۰۰۰ تومان', share_percent: '29.03' },
  ],
}

/**
 * Insights in all four severities at once.
 *
 * The screen is required to distinguish severities without relying on colour,
 * and to state plainly when there is nothing to report — so a fixture with a
 * single insight would leave most of that untested.
 */
export const INSIGHTS: InsightsResponse = {
  year: 1405,
  month: 6,
  label: 'شهریور ۱۴۰۵',
  insights: [
    {
      kind: 'budget_pace',
      severity: 'warning',
      title: 'سرعت هزینه در رستوران و کافه',
      message: 'هزینه این دسته از سرعت معمول بودجه بیشتر است.',
      icon: 'trending-up',
      metric: { consumed_percent: '120.00' },
      action: '/budgets',
    },
    {
      kind: 'overdue_debt',
      severity: 'attention',
      title: 'بدهی سررسید گذشته',
      message: 'یک بدهی از تاریخ سررسید گذشته است.',
      icon: 'alert-triangle',
      metric: { overdue_count: 1 },
      action: '/debts',
    },
    {
      kind: 'savings_rate',
      severity: 'positive',
      title: 'نرخ پس‌انداز این ماه',
      message: '۴۷٪ از درآمد این ماه پس‌انداز شده است.',
      icon: 'piggy-bank',
      metric: { savings_percent: '47.00' },
      action: null,
    },
    {
      kind: 'net_worth_growth',
      severity: 'info',
      title: 'روند دارایی خالص',
      message: 'ارزش دارایی خالص نسبت به ماه گذشته ۹٪ رشد کرده است.',
      icon: 'line-chart',
      metric: { change_percent: '8.70' },
      action: '/assets',
    },
  ],
  counts: { attention: 1, warning: 1, positive: 1, info: 1 },
}

// ---------------------------------------------------------------------------
// Bank-SMS import
//
// Staging fixtures follow the same rules as the budget ones: `*_display`
// strings carry Persian digits (the server really sends them; the response
// interceptor transliterates them), and every field the serializers send is
// present, so a page reading a wrong key sees `undefined` loudly in tests.
// ---------------------------------------------------------------------------

/** One undecided expense item, exactly as `SmsImportItemSerializer` sends it. */
export const SMS_ITEM_PENDING = {
  id: 101,
  raw_text: 'بانک ملت: خرید کارت ... مبلغ ۲۵۰,۰۰۰ ریال ... موجودی ۱۲,۰۰۰,۰۰۰ ریال',
  sender: '+989100000000',
  bank: 'mellat',
  bank_label: 'بانک ملت',
  is_transaction: true,
  noise_kind: '',
  card_last4: '1234',
  merchant: 'فروشگاه',
  direction: 'expense' as const,
  direction_label: 'هزینه',
  direction_pattern: 'card_purchase',
  amount: '25000.00',
  amount_display: '۲۵٬۰۰۰ تومان',
  amount_unit: 'toman',
  amount_unit_assumed: false,
  balance_after: '1200000.00',
  balance_display: '۱٬۲۰۰٬۰۰۰ تومان',
  balance_label: 'موجودی',
  occurred_on: '2026-08-20',
  date_display: '۲۹ مرداد ۱۴۰۵',
  date_assumed: false,
  date_source: 'message',
  confidence: 0.92,
  confidence_percent_display: '۹۲٪',
  confidence_label: 'اطمینان بالا',
  field_confidence: {},
  warnings: [],
  category: null,
  category_detail: null,
  account: null,
  account_name: null,
  spending_type: '',
  description: 'خرید کارت',
  note: '',
  status: 'pending' as const,
  status_label: 'در انتظار بررسی',
  transaction: null,
  is_ready: false,
}

/** A non-transaction message staged for transparency, never committed. */
export const SMS_ITEM_NOISE = {
  ...SMS_ITEM_PENDING,
  id: 102,
  raw_text: 'بانک ملت: رمز پویا برای خرید ...',
  is_transaction: false,
  noise_kind: 'otp',
  direction: '' as const,
  direction_label: 'نامشخص',
  amount: null,
  amount_display: null,
  balance_after: null,
  balance_display: null,
  status: 'noise' as const,
  status_label: 'غیرتراکنشی',
  is_ready: false,
}

export const SMS_BATCH = {
  id: 1,
  period_year: 1405,
  period_month: 5,
  period_label: 'مرداد ۱۴۰۵',
  source_label: 'بانک ملت',
  account: 5,
  account_name: 'بانک ملت',
  status: 'reviewing' as const,
  status_label: 'در بررسی',
  note: '',
  counts: { total: 2, pending: 1, imported: 0, skipped: 0, duplicate: 0, noise: 1 },
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-01T00:00:00Z',
  committed_at: null,
}

export const SMS_BATCH_DETAIL = {
  ...SMS_BATCH,
  items: [SMS_ITEM_PENDING, SMS_ITEM_NOISE],
}

export const SMS_BATCHES_PAGE = {
  count: 1,
  page: 1,
  page_size: 50,
  total_pages: 1,
  next: null,
  previous: null,
  results: [SMS_BATCH],
}

export const SMS_REMINDER = {
  should_remind: true,
  dismissed: false,
  within_window: true,
  window_days: 10,
  current_year: 1405,
  current_month: 6,
  current_label: 'شهریور ۱۴۰۵',
  days_elapsed: 3,
  suggested_year: 1405,
  suggested_month: 5,
  suggested_label: 'مرداد ۱۴۰۵',
  has_batch: false,
  has_committed_batch: false,
  pending_count: 0,
  message: 'ماه مرداد ۱۴۰۵ تمام شد؛ پیامک‌های بانکی آن را وارد کنید تا تراکنش‌ها و موجودی‌ها ثبت شود.',
}

/** Drift on purpose, so the reconcile button is reachable in tests. */
export const SMS_RECONCILIATION = {
  available: true,
  message: 'موجودی اعلام‌شده با دفتر شما اختلاف دارد؛ می‌توانید موجودی اولیه حساب را هماهنگ کنید.',
  account_id: 5,
  account_name: 'بانک ملت',
  reading_amount: '1200000.00',
  reading_amount_display: '۱٬۲۰۰٬۰۰۰ تومان',
  reading_date: '2026-08-20',
  reading_label: 'موجودی',
  later_income: '0.00',
  later_expense: '0.00',
  implied_opening_balance: '1200000.00',
  implied_opening_balance_display: '۱٬۲۰۰٬۰۰۰ تومان',
  current_opening_balance: '0.00',
  current_opening_balance_display: '۰ تومان',
  drift: '1200000.00',
  drift_display: '۱٬۲۰۰٬۰۰۰ تومان',
  matches: false,
}

/**
 * The automatic-reading switch, off — the state a fresh account is in.
 *
 * Copied from a real `GET /api/sms/auto-import/` response rather than written
 * to match the type: a hand-written fixture is how a payload mismatch survives.
 */
export const SMS_AUTO_IMPORT = {
  enabled: false,
  last_checked_at: null,
  last_checked_label: null,
  last_check: {},
  imported_from_sms_count: 0,
  pending_count: 0,
  message: 'دریافت خودکار خاموش است؛ پیامک‌ها به‌صورت خودکار بررسی نمی‌شوند.',
}

/** The same switch after a check has run and messages are waiting to review. */
export const SMS_AUTO_IMPORT_ON = {
  enabled: true,
  last_checked_at: '2026-09-23T12:02:00Z',
  last_checked_label: 'چهارشنبه 1 مهر 1405 — 15:32',
  last_check: {
    checked: 12,
    new_transactions: 3,
    new_messages: 3,
    not_transaction: 0,
    duplicate: 0,
    without_new: 9,
  },
  imported_from_sms_count: 12,
  pending_count: 3,
  message: '3 تراکنش از پیامک در انتظار بررسی است.',
}

/** What `POST /api/sms/auto-import/sync/` answers with when it finds something. */
export const SMS_SYNC_RESULT = {
  batch_id: 42,
  period: { year: 1405, month: 5, label: 'مرداد 1405' },
  summary: {
    checked: 12,
    new_transactions: 3,
    new_messages: 3,
    not_transaction: 0,
    duplicate: 0,
    without_new: 9,
  },
  pending_count: 3,
  message: '12 پیامک بررسی شد. 3 تراکنش جدید پیدا شد. 9 پیامک تراکنش جدیدی نداشت.',
}

/** The same call when the text held nothing that was not already known. */
export const SMS_SYNC_RESULT_EMPTY = {
  batch_id: null,
  period: { year: 1405, month: 5, label: 'مرداد 1405' },
  summary: {
    checked: 4,
    new_transactions: 0,
    new_messages: 0,
    not_transaction: 0,
    duplicate: 4,
    without_new: 4,
  },
  pending_count: 0,
  message: '4 پیامک بررسی شد. تراکنش جدیدی پیدا نشد. 4 پیامک تراکنش جدیدی نداشت.',
}

// ---------------------------------------------------------------------------
// Server stub
// ---------------------------------------------------------------------------
/** The subset of an axios response body our stub produces. */
interface AxiosLikeResponse {
  data: unknown
  status: number
  statusText: string
  headers: Record<string, string>
  config: unknown
}

export interface RecordedCall {
  method: string
  url: string
  body: Record<string, unknown>
}

/**
 * The slice of an axios request config the stub reads.
 *
 * `validateStatus` is `| null` in axios's own `InternalAxiosRequestConfig`, so
 * it must be `| null` here too — otherwise the adapter function is not
 * assignable to `AxiosAdapter` and `http.defaults.adapter = ...` is a type
 * error.
 */
interface StubRequestConfig {
  method?: string
  url?: string
  data?: unknown
  params?: Record<string, unknown>
  validateStatus?: ((status: number) => boolean) | null
}

export interface ServerStubOptions {
  /** Status for POST/PATCH/PUT. Anything >= 400 is treated as a failure. */
  writeStatus?: number
  /** Body returned for a failed write. */
  writeErrorBody?: unknown
  /** Canned response per path fragment. Checked before the defaults. */
  routes?: Record<string, { status?: number; body: unknown }>
  /**
   * Hold every response for this many milliseconds.
   *
   * Lets a test observe the pending branch — the product spec forbids a blank
   * screen while data loads, and that is only testable if the response can be
   * delayed deterministically.
   */
  delayMs?: number
  /** Initial `GET /sms/auto-import/` body. Defaults to the switch being off. */
  autoImport?: unknown
  /** `POST /sms/auto-import/sync/` body. Defaults to a run that found three. */
  syncResult?: unknown
}

export interface ServerStub {
  calls: RecordedCall[]
  /** Every call made to a mutating verb. */
  writes: RecordedCall[]
  restore: () => void
}

/**
 * Failure reasons from adapters, so a broken stub is loud instead of silent.
 *
 * Axios swallows adapter rejections into the normalised error the UI renders,
 * which makes a bug in the harness look like a bug in the component. Keeping the
 * raw reason here means a test failure names the actual cause.
 */
export const adapterErrors: string[] = []

/**
 * Install a deterministic fake API on the shared `http` instance.
 *
 * Defaults cover the endpoints the form dialogs read on mount (categories,
 * accounts). `routes` overrides any of them for a specific test.
 *
 * ## Why this has to call `settle` itself
 *
 * A custom axios adapter is responsible for its own status handling: axios core
 * simply takes the adapter's promise and runs the response transforms on it.
 * The built-in adapters call `settle`, which is what turns a 4xx into a
 * rejection. An adapter that always resolves makes every error path in the app
 * unreachable — 400s and 401s look like successes — so the status check is
 * reproduced here deliberately.
 */
export function installServerStub(options: ServerStubOptions = {}): ServerStub {
  const calls: RecordedCall[] = []
  const original = http.defaults.adapter
  adapterErrors.length = 0

  // Mutated by the toggle and the check, so the read that follows sees the
  // change — see the note where it is used.
  let autoImportState: Record<string, unknown> = {
    ...((options.autoImport as Record<string, unknown>) ?? SMS_AUTO_IMPORT),
  }

  const json = (body: unknown, status: number, config: unknown = {}) => ({
    data: body,
    status,
    statusText: status >= 400 ? 'Error' : 'OK',
    headers: { 'content-type': 'application/json' },
    config,
  })

  // Bound to the config of the request being handled, so every response is
  // shaped like a real axios response and can be settled against its own
  // `validateStatus`.
  let requestConfig: StubRequestConfig = {}

  // A function declaration rather than a const arrow: `handle` below is
  // referenced only at call time, but declaring it this way keeps the temporal
  // dead zone out of the picture entirely.
  function reply(body: unknown, status: number) {
    return json(body, status, requestConfig)
  }

  http.defaults.adapter = (async (config: StubRequestConfig) => {
    requestConfig = config
    if (options.delayMs) {
      await new Promise((resolve) => setTimeout(resolve, options.delayMs))
    }
    let response: AxiosLikeResponse
    try {
      response = await handle(config)
    } catch (error) {
      adapterErrors.push(
        `${String(config.method)} ${String(config.url)} → ${(error as Error)?.message ?? String(error)}`,
      )
      throw error
    }

    // Mirror what axios's built-in adapters do: honour `validateStatus` and
    // reject with an AxiosError so `normalizeError` sees a real failure.
    const validate = config.validateStatus ?? ((status: number) => status >= 200 && status < 300)
    if (!validate(response.status)) {
      const error = new AxiosError(
        `Request failed with status code ${response.status}`,
        response.status >= 500 ? AxiosError.ERR_BAD_RESPONSE : AxiosError.ERR_BAD_REQUEST,
        config as never,
        undefined,
        response as never,
      )
      throw error
    }

    return response
  }) as unknown as typeof http.defaults.adapter

  async function handle(config: StubRequestConfig) {
    // Axios passes the method lower-cased through the adapter, but normalising
    // here keeps the recorded calls readable and the `writes` filter honest.
    const method = (config.method ?? 'get').toUpperCase()
    // Axios keeps query parameters in `config.params`, not appended to the
    // URL — the adapter sees them separately. Fold them in so route matching
    // and the recorded call both reflect what the component actually asked
    // for (`/categories/picker/?kind=income`).
    const params = config.params as Record<string, unknown> | undefined
    const search = params
      ? new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined && v !== null && v !== '')
            .map(([k, v]) => [k, String(v)]),
        ).toString()
      : ''
    const path = config.url ?? ''
    const url = search ? `${path}${path.includes('?') ? '&' : '?'}${search}` : path

    let body: Record<string, unknown> = {}
    if (typeof config.data === 'string') {
      try {
        body = JSON.parse(config.data) as Record<string, unknown>
      } catch {
        body = {}
      }
    } else if (config.data && typeof config.data === 'object') {
      body = config.data as Record<string, unknown>
    }

    calls.push({ method, url, body })

    // Explicit overrides win.
    for (const [fragment, response] of Object.entries(options.routes ?? {})) {
      if (url.includes(fragment)) {
        return reply(response.body, response.status ?? 200)
      }
    }

    // The automatic-reading switch is *stateful* across calls, because the
    // whole point of it is a transition: turning it on has to be visible to the
    // read that follows, or a test could not tell a real toggle from a
    // component that redraws itself.
    if (method === 'GET' && url.includes('/sms/auto-import')) {
      return reply(autoImportState, 200)
    }
    if (method === 'PATCH' && url.includes('/sms/auto-import')) {
      const enabled = Boolean(body.enabled)
      autoImportState = {
        ...autoImportState,
        enabled,
        message: enabled
          ? 'روشن است؛ هنوز بررسی‌ای انجام نشده است.'
          : 'دریافت خودکار خاموش است؛ پیامک‌ها به‌صورت خودکار بررسی نمی‌شوند.',
      }
      return reply(autoImportState, 200)
    }
    if (method === 'POST' && url.includes('/sms/auto-import/sync')) {
      const result = options.syncResult ?? SMS_SYNC_RESULT
      const summary = (result as { summary?: unknown }).summary ?? {}
      autoImportState = {
        ...autoImportState,
        last_checked_at: '2026-09-23T12:02:00Z',
        last_checked_label: 'چهارشنبه 1 مهر 1405 — 15:32',
        last_check: summary,
        pending_count: (result as { pending_count?: number }).pending_count ?? 0,
        message: (result as { message?: string }).message ?? '',
      }
      return reply(result, 200)
    }

    if (method === 'GET') {
      if (url.includes('/categories/picker')) {
        return reply(url.includes('kind=income') ? CATEGORIES_INCOME : CATEGORIES_EXPENSE, 200)
      }
      if (url.includes('/accounts/picker')) {
        return reply([ACCOUNT], 200)
      }
      if (url.includes('/accounts')) {
        return reply(ACCOUNTS_PAGE, 200)
      }
      if (url.includes('/categories/meta')) {
        return reply({ icons: ['tag', 'wallet'], colors: ['#3566e8'], kinds: [] }, 200)
      }
      if (url.includes('/categories/grouped')) {
        return reply([], 200)
      }
      if (url.includes('/categories')) {
        return reply({ ...ACCOUNTS_PAGE, results: CATEGORIES_EXPENSE }, 200)
      }
      if (url.includes('/transactions/recent')) {
        return reply([TRANSACTION], 200)
      }      if (url.includes('/transactions/summary')) {
        return reply(
          {
            income_total: '5000000.00',
            income_total_display: '۵٬۰۰۰٬۰۰۰ تومان',
            expense_total: '3800000.00',
            expense_total_display: '۳٬۸۰۰٬۰۰۰ تومان',
            net: '1200000.00',
            net_display: '۱٬۲۰۰٬۰۰۰ تومان',
            count: 1,
          },
          200,
        )
      }
      if (url.includes('/transactions')) {
        return reply({ ...ACCOUNTS_PAGE, results: [TRANSACTION] }, 200)
      }
      // Feature screens. Each is checked before `return reply({}, 200)` so an
      // unregistered path fails loudly in a test rather than rendering an empty
      // screen that looks like a product bug.
      if (url.includes('/budgets/performance')) {
        return reply(
          {
            analysis: BUDGET_ANALYSIS,
            // Mirrors the real payload key-for-key. `total_categories` — not
            // `total` — is what the backend sends, and getting this wrong is
            // exactly how the page shipped rendering `undefined`.
            summary: { safe: 1, normal: 0, near_limit: 0, over: 1, total_categories: 2 },
            top_spending: [
              {
                category_id: 3,
                category_name: 'رستوران و کافه',
                category_full_path: 'رستوران و کافه',
                category_icon: 'coffee',
                category_color: '#d64545',
                spent: '3600000.00',
                transaction_count: 7,
              },
            ],
          },
          200,
        )
      }
      if (url.includes('/budgets/analysis') || url.includes('/budgets/current')) {
        return reply(BUDGET_ANALYSIS, 200)
      }
      if (url.includes('/debts/summary')) {
        return reply(DEBT_SUMMARY, 200)
      }
      if (url.includes('/debts/upcoming')) {
        return reply([DEBT], 200)
      }
      if (/\/debts\/\d+/.test(url)) {
        return reply(DEBT, 200)
      }
      if (url.includes('/debts')) {
        return reply({ ...ACCOUNTS_PAGE, results: [DEBT] }, 200)
      }
      if (url.includes('/assets/summary')) {
        return reply(ASSET_SUMMARY, 200)
      }
      if (url.includes('/assets/breakdown')) {
        return reply(ASSET_SUMMARY.by_type, 200)
      }
      if (url.includes('/assets')) {
        return reply({ ...ACCOUNTS_PAGE, results: [ASSET] }, 200)
      }
      if (url.includes('/net-worth/history')) {
        return reply({ history: NET_WORTH_HISTORY }, 200)
      }
      if (url.includes('/net-worth')) {
        return reply(NET_WORTH, 200)
      }
      if (url.includes('/reports')) {
        return reply(REPORTS, 200)
      }
      if (url.includes('/insights')) {
        return reply(INSIGHTS, 200)
      }
      // Bank-SMS import. Order matters: the reminder first, then the
      // reconcile detail action (its URL still contains `/sms/batches/{id}`),
      // then the batch detail, then the paginated list.
      if (url.includes('/sms/reminder')) {
        return reply(SMS_REMINDER, 200)
      }
      if (/\/sms\/batches\/\d+\/reconcile\/$/.test(url)) {
        return reply(SMS_RECONCILIATION, 200)
      }
      if (/\/sms\/batches\/\d+\/$/.test(url)) {
        return reply(SMS_BATCH_DETAIL, 200)
      }
      if (url.includes('/sms/batches')) {
        return reply(SMS_BATCHES_PAGE, 200)
      }
      if (url.includes('/auth/me')) {
        return reply(
          {
            id: 1,
            email: 'demo@mymoney.ir',
            first_name: 'سارا',
            last_name: 'محمدی',
            display_name: 'سارا محمدی',
            full_name: 'سارا محمدی',
            date_joined: '2026-01-01T00:00:00Z',
          },
          200,
        )
      }
      if (url.includes('/dashboard')) {
        return reply(DASHBOARD, 200)
      }
      if (url.includes('/net-worth')) {
        return reply({ history: [] }, 200)
      }
      return reply({}, 200)
    }

    // Writes.
    const status = options.writeStatus ?? 201
    if (status >= 400) {
      return reply(
        options.writeErrorBody ?? {
          detail: 'اطلاعات ارسالی معتبر نیست.',
          errors: {},
        },
        status,
      )
    }
    return reply({ id: 99, ...body }, status)
  }

  return {
    calls,
    // A getter, not a snapshot: the array is empty at install time, so a plain
    // property would freeze `writes` at zero forever.
    get writes() {
      return calls.filter((call) => call.method !== 'GET')
    },
    restore() {
      http.defaults.adapter = original
    },
  }
}

// ---------------------------------------------------------------------------
// Render wrapper
// ---------------------------------------------------------------------------

/** A QueryClient that never retries, so a failure surfaces on the first pass. */
export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  })
}

/**
 * Wraps a component in everything it needs: routing for `Link`/`useNavigate`,
 * a QueryClient, and the auth context. `initialEntries` lets a flow test start
 * on a deep route.
 *
 * `AuthProvider` is included even for components that do not read `useAuth`
 * directly — it is part of the app's real provider stack, and a test that omits
 * it would exercise a tree the app never renders.
 */
export function makeWrapper(initialEntries: string[] = ['/']) {
  const queryClient = makeQueryClient()

  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <MemoryRouter initialEntries={initialEntries}>
        <QueryClientProvider client={queryClient}>
          <ThemeProvider>
            <AuthProvider>
              <ToastProvider>{children}</ToastProvider>
            </AuthProvider>
          </ThemeProvider>
        </QueryClientProvider>
      </MemoryRouter>
    )
  }
}

/**
 * Mount the real `App` — router, query client and auth provider, mirroring
 * `main.tsx` — and start it on `initialEntries`.
 *
 * Distinct from `makeWrapper`, which mounts a single component. Use this when
 * the assertion is about a whole *screen*: the route table, the app shell and
 * the page it resolves to. `App` owns the route table, so it is mounted
 * directly inside the router rather than nested under a second `<Routes>` —
 * nesting would shadow it and render nothing.
 */
export function renderApp(initialEntries: string[] = ['/']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <QueryClientProvider client={makeQueryClient()}>
        <ThemeProvider>
          <AuthProvider>
            <ToastProvider>
              <App />
            </ToastProvider>
          </AuthProvider>
        </ThemeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

// ---------------------------------------------------------------------------
// Assertions shared across suites
// ---------------------------------------------------------------------------
/**
 * Vocabulary the product explicitly forbids.
 *
 * The spec's product principle is that the app reports what it observes about
 * the *money*, never a judgement about the *person*. Copy like
 * «شما در مدیریت پول خود ضعیف عمل کردهاید» must not appear anywhere.
 */
const ACCUSATORY = [
  'ضعیف',
  'بد عمل',
  'اشتباه',
  'ناتوان',
  'بی‌دقت',
  'غیرمسئولانه',
  'شما باید',
  'فاجعه',
  'بدون مدیریت',
  'شکست خورد',
]

export function findAccusatoryCopy(text: string): string[] {
  return ACCUSATORY.filter((word) => text.includes(word))
}

export { vi }
