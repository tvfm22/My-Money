/**
 * Shared API types.
 *
 * These mirror the DRF serializers. Money and percentage values arrive as
 * **decimal strings** (e.g. `"250000.00"`), never JSON numbers, so JavaScript
 * floating-point can never round a Toman amount. Each money field has a
 * sibling `*_display` field carrying the pre-formatted Persian string the UI
 * actually renders.
 */

// ---------------------------------------------------------------------------
// Envelopes
// ---------------------------------------------------------------------------

/** The shape `StandardPagination` returns. */
export interface Paginated<T> {
  count: number
  page: number
  page_size: number
  total_pages: number
  next: string | null
  previous: string | null
  results: T[]
}

/** Error bodies produced by `api_exception_handler`. */
export interface ApiError {
  detail: string
  errors?: Record<string, string[]>
  /** HTTP status, when the failure came back from the server at all. */
  status?: number
}

// ---------------------------------------------------------------------------
// Users and auth
// ---------------------------------------------------------------------------

export interface User {
  id: number
  email: string
  first_name: string
  last_name: string
  display_name: string
  full_name: string
  date_joined: string
}

export interface AuthTokens {
  access: string
  refresh: string
}

export interface LoginResponse extends AuthTokens {
  user: User
}

// ---------------------------------------------------------------------------
// Categories
// ---------------------------------------------------------------------------

export type CategoryKind = 'expense' | 'income'

export interface Category {
  id: number
  name: string
  kind: CategoryKind
  icon: string
  color: string
  parent: number | null
  parent_name: string | null
  full_path: string
  is_subcategory: boolean
  depth: number
  is_default: boolean
  is_active: boolean
  sort_order: number
  children?: Category[]
}

export interface CategoryPickerItem {
  id: number
  name: string
  kind: CategoryKind
  icon: string
  color: string
  parent: number | null
}

export interface CategoryMeta {
  icons: string[]
  colors: string[]
  kinds: Array<{ value: CategoryKind; label: string }>
}

// ---------------------------------------------------------------------------
// Accounts
// ---------------------------------------------------------------------------

export type AccountType =
  | 'bank'
  | 'cash'
  | 'card'
  | 'investment'
  | 'savings'
  | 'credit'
  | 'other'

export interface Account {
  id: number
  name: string
  account_type: AccountType
  account_type_label: string
  opening_balance: string
  opening_balance_display: string
  current_balance: string
  current_balance_display: string
  income_total: string
  income_total_display: string
  expense_total: string
  expense_total_display: string
  color: string
  icon: string
  institution: string
  include_in_total: boolean
  is_active: boolean
  sort_order: number
  transactions_count?: number
  created_at: string
  updated_at: string
}

// ---------------------------------------------------------------------------
// Transactions
// ---------------------------------------------------------------------------

export type TransactionType = 'expense' | 'income'

export interface Tag {
  id: number
  name: string
  color: string
  usage_count?: number
}

export interface Transaction {
  id: number
  transaction_type: TransactionType
  transaction_type_label: string
  amount: string
  amount_display: string
  signed_amount: string
  category: number
  category_detail: CategoryPickerItem | null
  account: number | null
  account_name: string | null
  account_icon: string | null
  occurred_on: string
  jalali_date: string
  date_display: string
  date_short: string
  /** Present on expenses; always absent on income. */
  spending_type: SpendingType | null
  spending_type_label: string | null
  description: string
  title: string
  note: string
  tags: Tag[]
  created_at: string
  updated_at: string
}

export interface TransactionSummary {
  income_total: string
  income_total_display: string
  expense_total: string
  expense_total_display: string
  net: string
  net_display: string
  count: number
}

// ---------------------------------------------------------------------------
// Budgets
// ---------------------------------------------------------------------------

export type BudgetStatus = 'safe' | 'normal' | 'near_limit' | 'over'
export type PaceStatus = 'behind' | 'on_track' | 'ahead'

export interface BudgetCategoryAnalysis {
  category_id: number
  category_name: string
  category_icon: string
  category_color: string
  category_full_path: string
  is_essential: boolean

  budgeted: string
  spent: string
  remaining: string
  consumed_percent: string
  elapsed_percent: string
  /** Percentage points consumed is ahead of elapsed. Signed. */
  pace_delta: string
  progress_ratio: string

  status: BudgetStatus
  status_label: string
  pace_state: PaceStatus
  message: string

  /** Null when there is not enough of the month elapsed to project a total. */
  projected_total: string | null
  projected_over_budget: boolean
  transaction_count: number
  days_elapsed: number
  days_in_month: number

  /** How far past the budget this category ran. Zero when within budget. */
  over_budget_amount: string

  budgeted_display: string
  spent_display: string
  remaining_display: string
  consumed_display: string
  elapsed_display: string
  over_budget_display: string
  projected_display: string | null
}

/**
 * The month's plan — what the user intended, before anything happened.
 *
 * Server shape. These were previously declared as flat fields on
 * `BudgetAnalysis`, which meant every read returned `undefined` and the budget
 * screens rendered blanks. The types now mirror the payload exactly; see the
 * note on `BudgetAnalysis`.
 */
export interface BudgetPlan {
  expected_income: string
  savings_target: string
  investment_target: string
  debt_payment_target: string
  /** Income minus every target and allocation. Negative means oversubscribed. */
  flexible_budget: string
  is_oversubscribed: boolean
  /** Budgeted amounts split by the stored `is_essential` flag. */
  essential_total: string
  flexible_total: string

  expected_income_display: string
  savings_target_display: string
  investment_target_display: string
  debt_payment_target_display: string
  flexible_budget_display: string
  essential_total_display: string
  flexible_total_display: string
}

/** Plan against actual, for the month as a whole. */
export interface BudgetTotals {
  budgeted: string
  spent: string
  remaining: string
  consumed_percent: string
  progress_ratio: string

  budgeted_display: string
  spent_display: string
  remaining_display: string
  consumed_display: string
}

/** What actually happened, independent of whether a budget exists. */
export interface BudgetActuals {
  income: string
  expense: string
  net: string
  income_display: string
  expense_display: string
}

/** How far through the month we are — the baseline consumption is judged against. */
export interface BudgetTime {
  days_elapsed: number
  days_in_month: number
  days_remaining: number
  elapsed_percent: string
  elapsed_display: string
}

/** Per-status tally on the performance view. */
export interface BudgetStatusSummary {
  safe: number
  normal: number
  near_limit: number
  over: number
  total_categories: number
}

/** A category with actual spending, budgeted or not. */
export interface BudgetTopSpender {
  category_id: number
  category_name: string
  category_full_path: string
  category_icon: string
  category_color: string
  /** Raw decimal string. Unlike the analysed categories this has no `_display`. */
  spent: string
  transaction_count: number
}

/**
 * A month of budget analysis.
 *
 * ## Why this is nested
 *
 * The payload groups the month into four blocks — `plan` (what was intended),
 * `totals` (plan vs actual), `actuals` (what happened) and `time` (how far
 * through the month we are) — because those are four genuinely different
 * things and the UI needs all of them side by side.
 *
 * This type used to declare every field flat. Nothing failed: `api.ts` casts
 * with an unchecked `http.get<T>`, so TypeScript was told a shape the server
 * never sends, and `analysis.total_spent_display` quietly evaluated to
 * `undefined` on every render. The budget screens showed blanks and zeros, and
 * the test suite stayed green because the fixtures were hand-written to match
 * the wrong type rather than copied from a real response.
 *
 * So: **fixtures for this type must be copied from a live response.** Hand-
 * writing one reintroduces exactly the bug this comment exists to prevent.
 */
export interface BudgetAnalysis {
  budget_id: number | null
  year: number
  month: number
  month_name: string
  label: string

  has_budget: boolean
  has_items: boolean
  is_active: boolean
  note: string

  plan: BudgetPlan
  totals: BudgetTotals
  actuals: BudgetActuals
  time: BudgetTime

  categories: BudgetCategoryAnalysis[]
  items: BudgetItem[]
}

/** `/api/budgets/performance/` — the analysis plus status tallies. */
export interface BudgetPerformance extends BudgetAnalysis {
  summary: BudgetStatusSummary
  top_spending: BudgetTopSpender[]
}

/**
 * A stored budget as returned by `/api/budgets/`.
 *
 * Every money field is a raw decimal string with no `_display` sibling — unlike
 * the analysed payloads, which do carry them. Format these client-side.
 */
export interface Budget {
  id: number
  year: number
  month: number
  month_name: string
  label: string
  expected_income: string
  savings_target: string
  investment_target: string
  debt_payment_target: string
  allocated_total: string
  committed_total: string
  flexible_budget: string
  is_oversubscribed: boolean
  note: string
  is_active: boolean
  items: BudgetItem[]
  created_at: string
  updated_at: string
}

/**
 * A single budgeted category, as returned inside a budget.
 *
 * Note there is no `amount_display`: the server sends raw decimal strings here
 * and the client formats them. An `amount_display` field was declared here for
 * a long time and never existed, which is harmless only because nothing read it
 * — the same class of fiction that made the budget screens render blanks.
 */
export interface BudgetItem {
  id: number
  category: number
  category_name: string
  category_icon: string
  category_color: string
  category_full_path: string
  amount: string
  is_essential: boolean
  note: string

  /** Live figures for the category, computed against actual spending. */
  spent: string
  remaining: string
  consumed_percent: string
  status: BudgetStatus
  status_label: string
  message: string

  created_at: string
  updated_at: string
}

// ---------------------------------------------------------------------------
// Debts
// ---------------------------------------------------------------------------

export type DebtDirection = 'payable' | 'receivable'
export type DebtStatusValue = 'active' | 'partial' | 'settled' | 'overdue'

export interface DebtPayment {
  id: number
  amount: string
  amount_display: string
  paid_on: string
  paid_on_display: string
  note: string
  account: number | null
  account_name: string | null
}

export interface Debt {
  id: number
  direction: DebtDirection
  direction_label: string
  counterparty: string
  principal: string
  principal_display: string
  paid_amount: string
  paid_display: string
  remaining_amount: string
  remaining_display: string
  paid_percent: string
  paid_percent_display: string
  status: DebtStatusValue
  status_label: string
  is_overdue: boolean
  is_settled: boolean
  days_until_due: number | null
  due_relative: string
  issued_on: string
  issued_on_display: string
  due_on: string
  due_on_display: string
  description: string
  note: string
  account: number | null
  account_name: string | null
  payments: DebtPayment[]
  payments_count: number
  created_at: string
  updated_at: string
}

export interface DebtSummary {
  payable_remaining: string
  payable_remaining_display: string
  payable_total: string
  payable_total_display: string
  receivable_remaining: string
  receivable_remaining_display: string
  receivable_total: string
  receivable_total_display: string
  net_position: string
  net_position_display: string
  overdue_count: number
  overdue_amount: string
  overdue_amount_display: string
  settled_count: number
  total_count: number
  open_count: number
  upcoming: Debt[]
}

// ---------------------------------------------------------------------------
// Assets
// ---------------------------------------------------------------------------

export type AssetType =
  | 'bank_account'
  | 'cash'
  | 'gold_fund'
  | 'gold'
  | 'stocks'
  | 'currency'
  | 'real_estate'
  | 'vehicle'
  | 'deposit'
  | 'crypto'
  | 'other'

export interface AssetValuation {
  id: number
  asset: number
  value: string
  value_display: string
  valued_on: string
  valued_on_display: string
  note: string
}

export interface Asset {
  id: number
  name: string
  asset_type: AssetType
  asset_type_label: string
  current_value: string
  current_value_display: string
  purchase_value: string
  purchase_value_display: string
  nominal_return: string
  nominal_return_display: string
  nominal_return_percent: string
  nominal_return_percent_display: string
  is_profitable: boolean
  total_cost_display: string
  quantity: string | null
  unit: string
  unit_price: string | null
  purchase_date: string | null
  purchase_date_display: string | null
  last_valued_on: { date: string; display: string; value: string } | null
  description: string
  note: string
  provider: string
  account: number | null
  owner_name: string
  include_in_net_worth: boolean
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface AssetSummary {
  current_value: string
  current_value_display: string
  purchase_value: string
  purchase_value_display: string
  included_value: string
  nominal_return: string
  nominal_return_display: string
  nominal_return_percent: string
  nominal_return_percent_display: string
  assets_count: number
  by_type: Array<{ type: string; total: string; display: string }>
  net_worth: NetWorth
}

export interface NetWorth {
  as_of: string
  total_assets: string
  total_assets_display: string
  total_liabilities: string
  total_liabilities_display: string
  net_worth: string
  net_worth_display: string
  total_receivables: string
  total_receivables_display: string
  assets_count: number
  liabilities_count: number
  receivables_count: number
  is_negative: boolean
}

export interface NetWorthPoint {
  year: number
  month: number
  key: string
  label: string
  month_name: string
  assets: string
  liabilities: string
  net_worth: string
}

// ---------------------------------------------------------------------------
// Dashboard and reports
// ---------------------------------------------------------------------------

export interface DashboardSummary {
  balance: string
  balance_display: string
  income: string
  income_display: string
  expense: string
  expense_display: string
  net: string
  net_display: string
  spendable: string
  spendable_display: string
  total_assets: string
  total_assets_display: string
  total_debts: string
  total_debts_display: string
  total_receivables: string
  total_receivables_display: string
  net_worth: string
  net_worth_display: string
  transactions_count: number
}

/**
 * Month-over-month change for one figure.
 *
 * `percent` is `null` when the previous month was zero — a percentage change
 * from nothing has no meaningful value, and reporting `∞` or a misleading
 * `100%` would be worse than saying nothing.
 */
export interface MonthComparison {
  current: string
  previous: string
  delta: string
  percent: string | null
  direction: 'up' | 'down' | 'flat'
  delta_display: string
  percent_display: string | null
}

/**
 * How the user classified an expense when recording it.
 *
 * `wasted` is a deliberate, judgement-free label — the point is to see where
 * money went, not to scold. Income never carries a spending type.
 */
export type SpendingType = 'essential' | 'flexible' | 'wasted'

/** One slice of the essential / flexible / other breakdown. */
export interface SpendingTypeBucket {
  key: string
  label: string
  amount: string
  amount_display: string
  share_percent: string
  share_display: string
  transaction_count: number
}

export interface SpendingTypes {
  total: string
  total_display: string
  /** Gregorian ISO bounds of the period covered. */
  start: string
  end: string
  buckets: SpendingTypeBucket[]
}

/**
 * The month the dashboard is showing.
 *
 * Carries the same time block as a budget analysis, plus the Jalali month
 * itself. The server calls the month name `name` here, not `month_name` — which
 * is the kind of small inconsistency worth mirroring exactly rather than
 * papering over, because the client is what has to read it.
 */
export interface DashboardMonth {
  year: number
  month: number
  name: string
  label: string
  days_elapsed: number
  days_in_month: number
  days_remaining: number
  elapsed_percent: string
  elapsed_display: string
}

/**
 * The dashboard's budget card — a subset of a full analysis.
 *
 * Same nested `plan` / `totals` blocks as `BudgetAnalysis`, and its
 * `top_categories` are byte-for-byte the same shape as that payload's
 * `categories`, so the same component renders both.
 */
export interface DashboardBudget {
  has_budget: boolean
  label: string
  categories_count: number
  plan: BudgetPlan
  totals: BudgetTotals
  top_categories: BudgetCategoryAnalysis[]
}

export interface Dashboard {
  greeting_name: string
  month: DashboardMonth
  summary: DashboardSummary
  comparison: {
    /** The Jalali month the figures are compared against, e.g. `مرداد ۱۴۰۵`. */
    previous_month_label: string
    income: MonthComparison
    expense: MonthComparison
  }
  budget: DashboardBudget
  spending_types: SpendingTypes
  recent_transactions: Transaction[]
  accounts_count: number
}

export interface CategorySpendSlice {
  category_id: number
  category_name: string
  icon: string
  color: string
  amount: string
  amount_display: string
  share_percent: string
  share_display: string
  count: number
}

export interface TrendPoint {
  year: number
  month: number
  key: string
  label: string
  label_short: string
  income: string
  expense: string
  net: string
}

export interface BudgetVsActualRow {
  category_id: number
  category_name: string
  icon: string
  color: string
  budgeted: string
  budgeted_display: string
  actual: string
  actual_display: string
  difference: string
  difference_display: string
  status: BudgetStatus
  /** How this category's actual spend splits across the three types. */
  spending_types?: SpendingTypes | null
}

export interface ReportsPayload {
  month: { year: number; month: number; label: string }
  spending_by_category: {
    total: string
    total_display: string
    slices: CategorySpendSlice[]
  }
  monthly_trend: TrendPoint[]
  /** The month's expenses split into essential / flexible / wasted. */
  spending_by_type: SpendingTypes
  budget_vs_actual: BudgetVsActualRow[]
  net_worth_history: NetWorthPoint[]
  asset_breakdown: Array<{ type: string; label: string; total: string; total_display: string; share_percent: string }>
}

// ---------------------------------------------------------------------------
// Insights
// ---------------------------------------------------------------------------

export type InsightSeverity = 'attention' | 'warning' | 'positive' | 'info'

export interface Insight {
  kind: string
  severity: InsightSeverity
  title: string
  message: string
  icon: string
  metric: Record<string, unknown>
  action: string | null
}

export interface InsightsResponse {
  year: number
  month: number
  label: string
  insights: Insight[]
  counts: Record<InsightSeverity, number>
}

/** A single point in an asset's valuation history, for the growth chart. */
export interface AssetGrowthPoint {
  date: string
  value: string
  asset_id: number
  asset_name: string
}

// ---------------------------------------------------------------------------
// Client-side query shapes
// ---------------------------------------------------------------------------

export interface TransactionFilters {
  search?: string
  transaction_type?: TransactionType | ''
  spending_type?: SpendingType | ''
  category?: number | ''
  category_group?: number | ''
  account?: number | ''
  tag?: number | ''
  date_from?: string
  date_to?: string
  month?: string
  period?: string
  amount_min?: string
  amount_max?: string
  ordering?: string
  page?: number
  page_size?: number
}

// ---------------------------------------------------------------------------
// Bank-SMS import
//
// Staging flow: paste → `POST /sms/parse/` (nothing saved) → `POST /sms/batches/`
// (rows staged for review) → classify each item → `POST /batches/{id}/commit/`
// (the ledger write). The review screen works on `SmsImportItem`s; only
// `commit` creates `Transaction`s.
// ---------------------------------------------------------------------------

export type SmsItemDirection = 'income' | 'expense' | ''

export type SmsItemStatus = 'pending' | 'imported' | 'skipped' | 'duplicate' | 'noise'

export type SmsBatchStatus = 'reviewing' | 'committed'

/**
 * One parsed message, exactly what `POST /sms/parse/` returns per message and
 * what a staged item was built from. Money arrives as decimal strings in
 * toman, like everywhere else in the API.
 */
export interface SmsPreviewMessage {
  raw_text: string
  bank: string
  bank_label: string
  sender: string
  is_transaction: boolean
  noise_kind: string
  direction: SmsItemDirection
  direction_pattern: string
  amount: string | null
  amount_unit: string
  amount_unit_assumed: boolean
  balance_after: string | null
  balance_label: string
  occurred_on: string | null
  date_source: string
  card_last4: string
  merchant: string
  description: string
  /** Decimal string, e.g. "0.92" — the label variants are what the UI shows. */
  confidence: string
  field_confidence: Record<string, string>
  warnings: string[]
  fingerprint: string
}

export interface SmsParsePreview {
  period: { year: number; month: number; label: string }
  summary: {
    total: number
    readable: number
    without_balance: number
    not_transaction: number
    low_confidence: number
  }
  messages: SmsPreviewMessage[]
}

export interface SmsBatchCounts {
  total: number
  pending: number
  imported: number
  skipped: number
  duplicate: number
  noise: number
}

/** A batch without its items — the history list entry. */
export interface SmsImportBatchSummary {
  id: number
  period_year: number
  period_month: number
  period_label: string
  source_label: string
  account: number | null
  account_name: string | null
  status: SmsBatchStatus
  status_label: string
  note: string
  counts: SmsBatchCounts
  created_at: string
  updated_at: string
  committed_at: string | null
}

/** A batch with every staged item — what the review screen loads. */
export interface SmsImportBatch extends SmsImportBatchSummary {
  items: SmsImportItem[]
}

export interface SmsImportItem {
  id: number
  // --- what arrived ------------------------------------------------------
  raw_text: string
  sender: string
  bank: string
  bank_label: string
  is_transaction: boolean
  noise_kind: string
  card_last4: string
  merchant: string
  // --- what was parsed ---------------------------------------------------
  direction: SmsItemDirection
  direction_label: string
  direction_pattern: string
  amount: string | null
  amount_display: string | null
  amount_unit: string
  amount_unit_assumed: boolean
  balance_after: string | null
  balance_display: string | null
  balance_label: string
  occurred_on: string | null
  date_display: string | null
  /** True when the date was not read from the message. */
  date_assumed: boolean
  date_source: string
  confidence: number
  confidence_percent_display: string
  confidence_label: string
  field_confidence: Record<string, string>
  warnings: string[]
  // --- what the user decided ----------------------------------------------
  category: number | null
  category_detail: CategoryPickerItem | null
  account: number | null
  account_name: string | null
  /** Empty on income rows — they carry no classification. */
  spending_type: SpendingType | ''
  description: string
  note: string
  status: SmsItemStatus
  status_label: string
  transaction: number | null
  is_ready: boolean
}

/** What `POST /sms/batches/{id}/commit/` answers with. */
export interface SmsCommitResponse {
  batch: SmsImportBatch
  imported_count: number
  missing_category_count: number
  incomplete_count: number
  not_transaction_count: number
  transactions: Transaction[]
  message: string
}

/**
 * What the balances printed in a batch imply about the account's opening
 * balance. `available: false` answers carry only a `message` explaining why.
 */
export interface SmsReconciliation {
  available: boolean
  message: string
  account_id?: number
  account_name?: string
  reading_amount?: string
  reading_amount_display?: string
  reading_date?: string | null
  reading_label?: string
  later_income?: string
  later_expense?: string
  implied_opening_balance?: string
  implied_opening_balance_display?: string
  current_opening_balance?: string
  current_opening_balance_display?: string
  drift?: string
  drift_display?: string
  matches?: boolean
  applied?: boolean
}

export interface SmsReminderState {
  should_remind: boolean
  dismissed: boolean
  within_window: boolean
  window_days: number
  current_year: number
  current_month: number
  current_label: string
  days_elapsed: number
  suggested_year: number
  suggested_month: number
  suggested_label: string
  has_batch: boolean
  has_committed_batch: boolean
  pending_count: number
  message: string
}

/** Payload for reading messages: a pasted blob, or explicit messages. */
export interface SmsParsePayload {
  text?: string
  source_label?: string
  period_year?: number
  period_month?: number
  account?: number | null
}

/** One staged item's editable decisions. */
export interface SmsItemPatch {
  category?: number | null
  account?: number | null
  spending_type?: SpendingType | ''
  status?: 'pending' | 'skipped'
  description?: string
  note?: string
  direction?: SmsItemDirection
  occurred_on?: string | null
}

/** Apply one decision to a whole selection of staged items. */
export interface SmsBulkPayload {
  item_ids: number[]
  category?: number | null
  account?: number | null
  spending_type?: SpendingType
  status?: 'pending' | 'skipped'
}

export interface SmsBulkUpdateResponse {
  updated_count: number
  skipped_count: number
  items: SmsImportItem[]
}
