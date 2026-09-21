/**
 * Typed API calls, grouped by resource.
 *
 * Components never call `http` directly — they call these functions through a
 * TanStack Query hook. Keeping the URLs and response shaping here means a
 * backend route change touches one file.
 */

import { http } from './client'

import type {
  Account,
  Asset,
  AssetGrowthPoint,
  AssetSummary,
  AssetValuation,
  Budget,
  BudgetAnalysis,
  BudgetItem,
  Category,
  CategoryMeta,
  CategoryPickerItem,
  Dashboard,
  Debt,
  DebtPayment,
  DebtSummary,
  InsightsResponse,
  LoginResponse,
  NetWorth,
  NetWorthPoint,
  Paginated,
  ReportsPayload,
  Tag,
  Transaction,
  TransactionFilters,
  TransactionSummary,
  User,
} from '../types'

/** Drop empty values so a cleared filter does not send `?category=`. */
function cleanParams(params: Record<string, unknown> | undefined): Record<string, unknown> {
  if (!params) return {}
  const result: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(params)) {
    if (value === '' || value === null || value === undefined) continue
    result[key] = value
  }
  return result
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export const authApi = {
  async login(email: string, password: string): Promise<LoginResponse> {
    const { data } = await http.post<LoginResponse>('/auth/login/', { email, password })
    return data
  },

  async register(payload: {
    email: string
    password: string
    password_confirm: string
    first_name?: string
    last_name?: string
  }): Promise<LoginResponse> {
    const { data } = await http.post<LoginResponse>('/auth/register/', payload)
    return data
  },

  async logout(refresh: string): Promise<void> {
    await http.post('/auth/logout/', { refresh })
  },

  async me(): Promise<User> {
    const { data } = await http.get<User>('/auth/me/')
    return data
  },

  async updateMe(payload: Partial<Pick<User, 'first_name' | 'last_name' | 'display_name'>>): Promise<User> {
    const { data } = await http.patch<User>('/auth/me/', payload)
    return data
  },

  async changePassword(payload: {
    current_password: string
    new_password: string
    new_password_confirm: string
  }): Promise<void> {
    await http.post('/auth/change-password/', payload)
  },

  async requestPasswordReset(email: string): Promise<{ detail: string }> {
    const { data } = await http.post<{ detail: string }>('/auth/password-reset/', { email })
    return data
  },

  async confirmPasswordReset(payload: {
    token: string
    new_password: string
    new_password_confirm: string
  }): Promise<{ detail: string }> {
    const { data } = await http.post<{ detail: string }>('/auth/password-reset/confirm/', payload)
    return data
  },
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

export const dashboardApi = {
  async get(): Promise<Dashboard> {
    const { data } = await http.get<Dashboard>('/dashboard/')
    return data
  },
}

// ---------------------------------------------------------------------------
// Categories
// ---------------------------------------------------------------------------

export const categoriesApi = {
  async list(kind?: 'expense' | 'income'): Promise<Paginated<Category>> {
    const { data } = await http.get<Paginated<Category>>('/categories/', {
      params: cleanParams({ kind, page_size: 200 }),
    })
    return data
  },

  /** Flat list for pickers — no pagination envelope. */
  async picker(kind?: 'expense' | 'income'): Promise<CategoryPickerItem[]> {
    const { data } = await http.get<CategoryPickerItem[]>('/categories/picker/', {
      params: cleanParams({ kind }),
    })
    return data
  },

  /** Parent/child tree, for grouped selects and the category manager. */
  async grouped(): Promise<Category[]> {
    const { data } = await http.get<Category[]>('/categories/grouped/')
    return data
  },

  async meta(): Promise<CategoryMeta> {
    const { data } = await http.get<CategoryMeta>('/categories/meta/')
    return data
  },

  async create(payload: Partial<Category>): Promise<Category> {
    const { data } = await http.post<Category>('/categories/', payload)
    return data
  },

  async update(id: number, payload: Partial<Category>): Promise<Category> {
    const { data } = await http.patch<Category>(`/categories/${id}/`, payload)
    return data
  },

  async remove(id: number): Promise<void> {
    await http.delete(`/categories/${id}/`)
  },
}

// ---------------------------------------------------------------------------
// Accounts
// ---------------------------------------------------------------------------

export const accountsApi = {
  async list(): Promise<Paginated<Account>> {
    const { data } = await http.get<Paginated<Account>>('/accounts/', {
      params: { page_size: 100 },
    })
    return data
  },

  async picker(): Promise<Account[]> {
    const { data } = await http.get<Account[]>('/accounts/picker/')
    return data
  },

  async summary(): Promise<{
    total: string
    total_display: string
    accounts: Account[]
    count: number
  }> {
    const { data } = await http.get('/accounts/summary/')
    return data
  },

  async create(payload: Partial<Account>): Promise<Account> {
    const { data } = await http.post<Account>('/accounts/', payload)
    return data
  },

  async update(id: number, payload: Partial<Account>): Promise<Account> {
    const { data } = await http.patch<Account>(`/accounts/${id}/`, payload)
    return data
  },

  async remove(id: number): Promise<void> {
    await http.delete(`/accounts/${id}/`)
  },
}

// ---------------------------------------------------------------------------
// Transactions
// ---------------------------------------------------------------------------

export const transactionsApi = {
  async list(filters: TransactionFilters = {}): Promise<Paginated<Transaction>> {
    const { data } = await http.get<Paginated<Transaction>>('/transactions/', {
      params: cleanParams(filters as Record<string, unknown>),
    })
    return data
  },

  async recent(limit = 8): Promise<Transaction[]> {
    const { data } = await http.get<Transaction[]>('/transactions/recent/', {
      params: { limit },
    })
    return data
  },

  async summary(filters: TransactionFilters = {}): Promise<TransactionSummary> {
    const { data } = await http.get<TransactionSummary>('/transactions/summary/', {
      params: cleanParams(filters as Record<string, unknown>),
    })
    return data
  },

  async get(id: number): Promise<Transaction> {
    const { data } = await http.get<Transaction>(`/transactions/${id}/`)
    return data
  },

  async create(payload: Record<string, unknown>): Promise<Transaction> {
    const { data } = await http.post<Transaction>('/transactions/', payload)
    return data
  },

  async update(id: number, payload: Record<string, unknown>): Promise<Transaction> {
    const { data } = await http.patch<Transaction>(`/transactions/${id}/`, payload)
    return data
  },

  async remove(id: number): Promise<void> {
    await http.delete(`/transactions/${id}/`)
  },

  async tags(): Promise<Tag[]> {
    const { data } = await http.get<Tag[]>('/transactions/tags/')
    return data
  },
}

// ---------------------------------------------------------------------------
// Budgets
// ---------------------------------------------------------------------------

export const budgetsApi = {
  async current(): Promise<{ budget: Budget | null; analysis: BudgetAnalysis }> {
    const { data } = await http.get('/budgets/current/')
    return data
  },

  async analysis(year?: number, month?: number): Promise<BudgetAnalysis> {
    const { data } = await http.get<BudgetAnalysis>('/budgets/analysis/', {
      params: cleanParams({ year, month }),
    })
    return data
  },

  async performance(year?: number, month?: number): Promise<{
    analysis: BudgetAnalysis
    summary: Record<string, number>
    /**
     * The largest actual spenders this month, budgeted or not.
     *
     * The field names come from `BudgetsViewSet.performance` — `spent` is a
     * decimal string and `transaction_count` is how many rows produced it.
     * There is no `spent_display` here; the backend sends raw money for this
     * list, unlike the analysed categories which carry display siblings.
     */
    top_spending: Array<{
      category_id: number
      category_name: string
      category_full_path: string
      category_icon: string
      category_color: string
      spent: string
      transaction_count: number
    }>
  }> {
    const { data } = await http.get('/budgets/performance/', {
      params: cleanParams({ year, month }),
    })
    return data
  },

  /**
   * Set a whole month's plan atomically. The server replaces the month's items
   * in one transaction, so a partial save cannot leave a half-planned budget.
   *
   * The field is called `allocations`, not `items`. It used to be sent as
   * `items` and the server silently ignored it — DRF drops unknown keys — so
   * editing the amounts and pressing save reported success and changed nothing.
   *
   * `is_essential` is optional here and the budget form no longer sends it. The
   * server keeps the flag, but the interface does not classify lines as
   * essential or flexible any more — that split belongs to actual spending, on
   * the dashboard, where it comes from each expense's own type. Sending an
   * explicit value from here would start overwriting stored flags again.
   */
  async plan(payload: {
    year?: number
    month?: number
    expected_income?: string
    savings_target?: string
    investment_target?: string
    debt_payment_target?: string
    note?: string
    allocations: Array<{ category: number; amount: string; is_essential?: boolean }>
  }): Promise<{ budget: Budget; analysis: BudgetAnalysis }> {
    const { data } = await http.post('/budgets/plan/', payload)
    return data
  },

  async copy(fromYear: number, fromMonth: number, toYear: number, toMonth: number): Promise<{
    budget: Budget
  }> {
    const { data } = await http.post('/budgets/copy/', {
      from_year: fromYear,
      from_month: fromMonth,
      to_year: toYear,
      to_month: toMonth,
    })
    return data
  },

  async items(budgetId: number): Promise<BudgetItem[]> {
    const { data } = await http.get<BudgetItem[]>(`/budgets/${budgetId}/items/`)
    return data
  },

  async createItem(payload: {
    budget: number
    category: number
    amount: string
    is_essential?: boolean
  }): Promise<BudgetItem> {
    const { data } = await http.post<BudgetItem>('/budget-items/', payload)
    return data
  },

  async updateItem(id: number, payload: Partial<BudgetItem>): Promise<BudgetItem> {
    const { data } = await http.patch<BudgetItem>(`/budget-items/${id}/`, payload)
    return data
  },

  async removeItem(id: number): Promise<void> {
    await http.delete(`/budget-items/${id}/`)
  },
}

// ---------------------------------------------------------------------------
// Debts
// ---------------------------------------------------------------------------

export const debtsApi = {
  async list(params: { direction?: string; status?: string } = {}): Promise<Paginated<Debt>> {
    const { data } = await http.get<Paginated<Debt>>('/debts/', {
      params: cleanParams({ ...params, page_size: 100 }),
    })
    return data
  },

  async summary(): Promise<DebtSummary> {
    const { data } = await http.get<DebtSummary>('/debts/summary/')
    return data
  },

  async upcoming(): Promise<Debt[]> {
    const { data } = await http.get<Debt[]>('/debts/upcoming/')
    return data
  },

  async get(id: number): Promise<Debt> {
    const { data } = await http.get<Debt>(`/debts/${id}/`)
    return data
  },

  async create(payload: Record<string, unknown>): Promise<Debt> {
    const { data } = await http.post<Debt>('/debts/', payload)
    return data
  },

  async update(id: number, payload: Record<string, unknown>): Promise<Debt> {
    const { data } = await http.patch<Debt>(`/debts/${id}/`, payload)
    return data
  },

  async remove(id: number): Promise<void> {
    await http.delete(`/debts/${id}/`)
  },

  async addPayment(
    debtId: number,
    payload: { amount: string; paid_on: string; note?: string; account?: number | null },
  ): Promise<DebtPayment> {
    const { data } = await http.post<DebtPayment>(`/debts/${debtId}/payments/`, payload)
    return data
  },

  async removePayment(debtId: number, paymentId: number): Promise<void> {
    await http.delete(`/debts/${debtId}/payments/${paymentId}/`)
  },
}

// ---------------------------------------------------------------------------
// Assets
// ---------------------------------------------------------------------------

export const assetsApi = {
  async list(): Promise<Paginated<Asset>> {
    const { data } = await http.get<Paginated<Asset>>('/assets/', {
      params: { page_size: 100 },
    })
    return data
  },

  async summary(): Promise<AssetSummary> {
    const { data } = await http.get<AssetSummary>('/assets/summary/')
    return data
  },

  async breakdown(): Promise<AssetSummary['by_type']> {
    const { data } = await http.get<AssetSummary['by_type']>('/assets/breakdown/')
    return data
  },

  async get(id: number): Promise<Asset> {
    const { data } = await http.get<Asset>(`/assets/${id}/`)
    return data
  },

  async create(payload: Record<string, unknown>): Promise<Asset> {
    const { data } = await http.post<Asset>('/assets/', payload)
    return data
  },

  async update(id: number, payload: Record<string, unknown>): Promise<Asset> {
    const { data } = await http.patch<Asset>(`/assets/${id}/`, payload)
    return data
  },

  async remove(id: number): Promise<void> {
    await http.delete(`/assets/${id}/`)
  },

  async valuations(assetId: number): Promise<AssetValuation[]> {
    const { data } = await http.get<AssetValuation[]>(`/assets/${assetId}/valuations/`)
    return data
  },

  async addValuation(
    assetId: number,
    payload: { value: string; valued_on: string; note?: string },
  ): Promise<AssetValuation> {
    const { data } = await http.post<AssetValuation>(
      `/assets/${assetId}/valuations/`,
      payload,
    )
    return data
  },

  async removeValuation(assetId: number, valuationId: number): Promise<void> {
    await http.delete(`/assets/${assetId}/valuations/${valuationId}/`)
  },

  async growth(assetId?: number): Promise<AssetGrowthPoint[]> {
    const { data } = await http.get<AssetGrowthPoint[]>('/assets/growth/', {
      params: cleanParams({ asset_id: assetId }),
    })
    return data
  },
}

export const netWorthApi = {
  async get(): Promise<NetWorth> {
    const { data } = await http.get<NetWorth>('/net-worth/')
    return data
  },

  async history(months = 12): Promise<{ history: NetWorthPoint[]; change?: Record<string, unknown> }> {
    const { data } = await http.get('/net-worth/history/', { params: { months } })
    return data
  },
}

// ---------------------------------------------------------------------------
// Reports and insights
// ---------------------------------------------------------------------------

export const reportsApi = {
  async all(params: { year?: number; month?: number; months?: number } = {}): Promise<ReportsPayload> {
    const { data } = await http.get<ReportsPayload>('/reports/', { params: cleanParams(params) })
    return data
  },

  async spendingByCategory(params: { year?: number; month?: number } = {}) {
    const { data } = await http.get('/reports/spending-by-category/', {
      params: cleanParams(params),
    })
    return data
  },

  async monthlyTrend(months = 6): Promise<{ series: ReportsPayload['monthly_trend']; months: number }> {
    const { data } = await http.get('/reports/monthly-trend/', { params: { months } })
    return data
  },

  async budgetVsActual(params: { year?: number; month?: number } = {}) {
    const { data } = await http.get('/reports/budget-vs-actual/', {
      params: cleanParams(params),
    })
    return data
  },
}

export const insightsApi = {
  async list(params: { year?: number; month?: number } = {}): Promise<InsightsResponse> {
    const { data } = await http.get<InsightsResponse>('/insights/', {
      params: cleanParams(params),
    })
    return data
  },
}
