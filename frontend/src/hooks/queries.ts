/**
 * TanStack Query hooks — one per resource.
 *
 * Query keys are centralised so invalidation is reliable: after saving a
 * transaction we invalidate `transactions`, `dashboard`, `budgets` and
 * `reports`, because a transaction changes all of them. Getting this wrong is
 * how a finance app ends up showing a stale balance, so the keys live here and
 * the mutation hooks below know exactly what to invalidate.
 */

import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from '@tanstack/react-query'

import {
  accountsApi,
  assetsApi,
  authApi,
  budgetsApi,
  categoriesApi,
  dashboardApi,
  debtsApi,
  insightsApi,
  netWorthApi,
  reportsApi,
  smsApi,
  transactionsApi,
} from '../services/api'
import type {
  Account,
  Asset,
  BudgetAnalysis,
  Category,
  CategoryKind,
  Dashboard,
  Debt,
  DebtSummary,
  InsightsResponse,
  NetWorth,
  NetWorthPoint,
  Paginated,
  ReportsPayload,
  SmsBulkPayload,
  SmsItemPatch,
  SmsParsePayload,
  SmsSyncPayload,
  Transaction,
  TransactionFilters,
  TransactionSummary,
  User,
} from '../types'

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------

export const queryKeys = {
  me: ['me'] as const,

  dashboard: ['dashboard'] as const,

  categories: (kind?: CategoryKind) => ['categories', kind ?? 'all'] as const,
  categoryPicker: (kind?: CategoryKind) => ['categories', 'picker', kind ?? 'all'] as const,
  categoryMeta: ['categories', 'meta'] as const,

  accounts: ['accounts'] as const,
  accountsSummary: ['accounts', 'summary'] as const,

  transactions: (filters?: TransactionFilters) => ['transactions', filters ?? {}] as const,
  transactionsRecent: (limit: number) => ['transactions', 'recent', limit] as const,
  transactionsSummary: (filters?: TransactionFilters) =>
    ['transactions', 'summary', filters ?? {}] as const,
  tags: ['tags'] as const,

  budgetsCurrent: ['budgets', 'current'] as const,
  budgetAnalysis: (year?: number, month?: number) => ['budgets', 'analysis', year, month] as const,
  budgetPerformance: (year?: number, month?: number) =>
    ['budgets', 'performance', year, month] as const,

  debts: (params?: Record<string, unknown>) => ['debts', params ?? {}] as const,
  debtSummary: ['debts', 'summary'] as const,
  debtsUpcoming: ['debts', 'upcoming'] as const,
  debt: (id: number) => ['debts', 'detail', id] as const,

  assets: ['assets'] as const,
  assetSummary: ['assets', 'summary'] as const,
  asset: (id: number) => ['assets', 'detail', id] as const,
  assetValuations: (id: number) => ['assets', id, 'valuations'] as const,

  netWorth: ['net-worth'] as const,
  netWorthHistory: (months: number) => ['net-worth', 'history', months] as const,

  reports: (params?: Record<string, unknown>) => ['reports', params ?? {}] as const,
  insights: (year?: number, month?: number) => ['insights', year, month] as const,

  smsBatches: ['sms', 'batches'] as const,
  smsBatch: (id: number) => ['sms', 'batch', id] as const,
  smsReminder: ['sms', 'reminder'] as const,
  smsReconcile: (id: number) => ['sms', 'reconcile', id] as const,
  smsAutoImport: ['sms', 'auto-import'] as const,
}

// ---------------------------------------------------------------------------
// Cache invalidation
// ---------------------------------------------------------------------------

/**
 * Everything a transaction affects.
 *
 * Balance, budget consumption and every dashboard figure are derived from
 * transactions, so any write to them invalidates all of this at once.
 */
function invalidateFinancialState(queryClient: ReturnType<typeof useQueryClient>): void {
  void queryClient.invalidateQueries({ queryKey: ['transactions'] })
  void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
  void queryClient.invalidateQueries({ queryKey: ['budgets'] })
  void queryClient.invalidateQueries({ queryKey: ['reports'] })
  void queryClient.invalidateQueries({ queryKey: ['insights'] })
  void queryClient.invalidateQueries({ queryKey: ['accounts'] })
}

/** Everything a debt or asset change affects (net worth feeds the dashboard). */
function invalidateNetWorthState(queryClient: ReturnType<typeof useQueryClient>): void {
  void queryClient.invalidateQueries({ queryKey: ['debts'] })
  void queryClient.invalidateQueries({ queryKey: ['assets'] })
  void queryClient.invalidateQueries({ queryKey: ['net-worth'] })
  void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
  void queryClient.invalidateQueries({ queryKey: ['reports'] })
  void queryClient.invalidateQueries({ queryKey: ['insights'] })
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export function useMe(options?: Partial<UseQueryOptions<User>>) {
  return useQuery({
    queryKey: queryKeys.me,
    queryFn: authApi.me,
    staleTime: 5 * 60_000,
    ...options,
  })
}

export function useUpdateProfile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: authApi.updateMe,
    onSuccess: (user) => {
      queryClient.setQueryData(queryKeys.me, user)
    },
  })
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

export function useDashboard() {
  return useQuery({
    queryKey: queryKeys.dashboard,
    queryFn: dashboardApi.get,
    // The dashboard is the home screen; refresh it when the tab regains focus
    // so a number is never stale from an earlier session.
    refetchOnWindowFocus: true,
  })
}

// ---------------------------------------------------------------------------
// Categories
// ---------------------------------------------------------------------------

export function useCategories(kind?: CategoryKind) {
  return useQuery({
    queryKey: queryKeys.categories(kind),
    queryFn: () => categoriesApi.list(kind),
    staleTime: 10 * 60_000,
  })
}

/** Flat, unpaginated list for pickers and chips. */
export function useCategoryPicker(kind?: CategoryKind) {
  return useQuery({
    queryKey: ['categories', 'picker', kind ?? 'all'] as const,
    queryFn: () => categoriesApi.picker(kind),
    staleTime: 10 * 60_000,
  })
}

/** Grouped parent/child tree. Used by the category picker and manager. */
export function useCategoryTree() {
  return useQuery({
    queryKey: ['categories', 'grouped'] as const,
    queryFn: categoriesApi.grouped,
    staleTime: 10 * 60_000,
  })
}

export function useCategoryMeta() {
  return useQuery({
    queryKey: queryKeys.categoryMeta,
    queryFn: categoriesApi.meta,
    // Design tokens never change during a session.
    staleTime: Infinity,
  })
}

export function useCreateCategory() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: categoriesApi.create,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['categories'] })
    },
  })
}

export function useUpdateCategory() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...payload }: { id: number } & Partial<Category>) =>
      categoriesApi.update(id, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['categories'] })
    },
  })
}

export function useDeleteCategory() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: categoriesApi.remove,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['categories'] })
    },
  })
}

// ---------------------------------------------------------------------------
// Accounts
// ---------------------------------------------------------------------------

export function useAccounts() {
  return useQuery({
    queryKey: queryKeys.accounts,
    queryFn: accountsApi.list,
  })
}

export function useAccountsSummary() {
  return useQuery({
    queryKey: queryKeys.accountsSummary,
    queryFn: accountsApi.summary,
  })
}

export function useCreateAccount() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: accountsApi.create,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['accounts'] })
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

export function useUpdateAccount() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...payload }: { id: number } & Partial<Account>) =>
      accountsApi.update(id, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['accounts'] })
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

export function useDeleteAccount() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: accountsApi.remove,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['accounts'] })
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

// ---------------------------------------------------------------------------
// Transactions
// ---------------------------------------------------------------------------

export function useTransactions(filters: TransactionFilters = {}) {
  return useInfiniteQuery({
    queryKey: queryKeys.transactions(filters),
    queryFn: ({ pageParam }) => transactionsApi.list({ ...filters, page: pageParam }),
    initialPageParam: 1,
    getNextPageParam: (lastPage) =>
      lastPage.next !== null ? lastPage.page + 1 : undefined,
    // Keep the previous result visible while a new filter set loads, so
    // filtering never flashes an empty list.
    placeholderData: (previous) => previous,
  })
}

export function useRecentTransactions(limit = 8) {
  return useQuery({
    queryKey: queryKeys.transactionsRecent(limit),
    queryFn: () => transactionsApi.recent(limit),
  })
}

export function useTransactionSummary(filters: TransactionFilters = {}) {
  return useQuery({
    queryKey: queryKeys.transactionsSummary(filters),
    queryFn: () => transactionsApi.summary(filters),
  })
}

export function useTags() {
  return useQuery({
    queryKey: queryKeys.tags,
    queryFn: transactionsApi.tags,
    staleTime: 5 * 60_000,
  })
}

export function useCreateTransaction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: transactionsApi.create,
    onSuccess: () => invalidateFinancialState(queryClient),
  })
}

export function useUpdateTransaction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...payload }: { id: number } & Record<string, unknown>) =>
      transactionsApi.update(id, payload),
    onSuccess: () => invalidateFinancialState(queryClient),
  })
}

export function useDeleteTransaction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: transactionsApi.remove,
    onSuccess: () => invalidateFinancialState(queryClient),
  })
}

// ---------------------------------------------------------------------------
// Budgets
// ---------------------------------------------------------------------------

export function useCurrentBudget() {
  return useQuery({
    queryKey: queryKeys.budgetsCurrent,
    queryFn: budgetsApi.current,
  })
}

export function useBudgetAnalysis(year?: number, month?: number) {
  return useQuery({
    queryKey: queryKeys.budgetAnalysis(year, month),
    queryFn: () => budgetsApi.analysis(year, month),
  })
}

export function useBudgetPerformance(year?: number, month?: number) {
  return useQuery({
    queryKey: queryKeys.budgetPerformance(year, month),
    queryFn: () => budgetsApi.performance(year, month),
  })
}

export function useSaveBudgetPlan() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: budgetsApi.plan,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['budgets'] })
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      void queryClient.invalidateQueries({ queryKey: ['insights'] })
    },
  })
}

export function useCopyBudget() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      fromYear,
      fromMonth,
      toYear,
      toMonth,
    }: {
      fromYear: number
      fromMonth: number
      toYear: number
      toMonth: number
    }) => budgetsApi.copy(fromYear, fromMonth, toYear, toMonth),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['budgets'] })
    },
  })
}

export function useCreateBudgetItem() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: budgetsApi.createItem,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['budgets'] })
    },
  })
}

export function useUpdateBudgetItem() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...payload }: { id: number } & Record<string, unknown>) =>
      budgetsApi.updateItem(id, payload as never),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['budgets'] })
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

export function useDeleteBudgetItem() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: budgetsApi.removeItem,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['budgets'] })
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

// ---------------------------------------------------------------------------
// Debts
// ---------------------------------------------------------------------------

export function useDebts(params: { direction?: string; status?: string } = {}) {
  return useQuery({
    queryKey: queryKeys.debts(params),
    queryFn: () => debtsApi.list(params),
  })
}

export function useDebtSummary() {
  return useQuery({
    queryKey: queryKeys.debtSummary,
    queryFn: debtsApi.summary,
  })
}

export function useUpcomingDebts() {
  return useQuery({
    queryKey: queryKeys.debtsUpcoming,
    queryFn: debtsApi.upcoming,
  })
}

export function useDebt(id: number) {
  return useQuery({
    queryKey: queryKeys.debt(id),
    queryFn: () => debtsApi.get(id),
    enabled: Number.isFinite(id) && id > 0,
  })
}

export function useCreateDebt() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: debtsApi.create,
    onSuccess: () => invalidateNetWorthState(queryClient),
  })
}

export function useUpdateDebt() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...payload }: { id: number } & Record<string, unknown>) =>
      debtsApi.update(id, payload),
    onSuccess: () => invalidateNetWorthState(queryClient),
  })
}

export function useDeleteDebt() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: debtsApi.remove,
    onSuccess: () => invalidateNetWorthState(queryClient),
  })
}

export function useAddDebtPayment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      debtId,
      ...payload
    }: {
      debtId: number
      amount: string
      paid_on: string
      note?: string
      account?: number | null
    }) => debtsApi.addPayment(debtId, payload),
    onSuccess: (_data, variables) => {
      invalidateNetWorthState(queryClient)
      void queryClient.invalidateQueries({ queryKey: queryKeys.debt(variables.debtId) })
    },
  })
}

export function useDeleteDebtPayment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ debtId, paymentId }: { debtId: number; paymentId: number }) =>
      debtsApi.removePayment(debtId, paymentId),
    onSuccess: (_data, variables) => {
      invalidateNetWorthState(queryClient)
      void queryClient.invalidateQueries({ queryKey: queryKeys.debt(variables.debtId) })
    },
  })
}

// ---------------------------------------------------------------------------
// Assets
// ---------------------------------------------------------------------------

export function useAssets() {
  return useQuery({
    queryKey: queryKeys.assets,
    queryFn: assetsApi.list,
  })
}

export function useAssetSummary() {
  return useQuery({
    queryKey: queryKeys.assetSummary,
    queryFn: assetsApi.summary,
  })
}

export function useAsset(id: number) {
  return useQuery({
    queryKey: queryKeys.asset(id),
    queryFn: () => assetsApi.get(id),
    enabled: Number.isFinite(id) && id > 0,
  })
}

export function useAssetValuations(assetId: number) {
  return useQuery({
    queryKey: queryKeys.assetValuations(assetId),
    queryFn: () => assetsApi.valuations(assetId),
    enabled: Number.isFinite(assetId) && assetId > 0,
  })
}

export function useAssetGrowth(assetId?: number) {
  return useQuery({
    queryKey: ['assets', 'growth', assetId ?? 'all'] as const,
    queryFn: () => assetsApi.growth(assetId),
  })
}

export function useCreateAsset() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: assetsApi.create,
    onSuccess: () => invalidateNetWorthState(queryClient),
  })
}

export function useUpdateAsset() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...payload }: { id: number } & Record<string, unknown>) =>
      assetsApi.update(id, payload),
    onSuccess: () => invalidateNetWorthState(queryClient),
  })
}

export function useDeleteAsset() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: assetsApi.remove,
    onSuccess: () => invalidateNetWorthState(queryClient),
  })
}

export function useAddValuation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      assetId,
      ...payload
    }: {
      assetId: number
      value: string
      valued_on: string
      note?: string
    }) => assetsApi.addValuation(assetId, payload),
    onSuccess: (_data, variables) => {
      invalidateNetWorthState(queryClient)
      void queryClient.invalidateQueries({
        queryKey: queryKeys.assetValuations(variables.assetId),
      })
      void queryClient.invalidateQueries({ queryKey: queryKeys.asset(variables.assetId) })
      void queryClient.invalidateQueries({ queryKey: ['assets', 'growth'] })
    },
  })
}

export function useDeleteValuation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ assetId, valuationId }: { assetId: number; valuationId: number }) =>
      assetsApi.removeValuation(assetId, valuationId),
    onSuccess: (_data, variables) => {
      invalidateNetWorthState(queryClient)
      void queryClient.invalidateQueries({
        queryKey: queryKeys.assetValuations(variables.assetId),
      })
    },
  })
}

// ---------------------------------------------------------------------------
// Net worth
// ---------------------------------------------------------------------------

export function useNetWorth() {
  return useQuery({
    queryKey: queryKeys.netWorth,
    queryFn: netWorthApi.get,
  })
}

export function useNetWorthHistory(months = 12) {
  return useQuery({
    queryKey: queryKeys.netWorthHistory(months),
    queryFn: () => netWorthApi.history(months),
  })
}

// ---------------------------------------------------------------------------
// Reports and insights
// ---------------------------------------------------------------------------

export function useReports(params: { year?: number; month?: number; months?: number } = {}) {
  return useQuery({
    queryKey: queryKeys.reports(params),
    queryFn: () => reportsApi.all(params),
  })
}

export function useInsights(year?: number, month?: number) {
  return useQuery({
    queryKey: queryKeys.insights(year, month),
    queryFn: () => insightsApi.list({ year, month }),
  })
}

// ---------------------------------------------------------------------------
// Bank-SMS import
// ---------------------------------------------------------------------------

export function useSmsBatches() {
  return useQuery({
    queryKey: queryKeys.smsBatches,
    queryFn: smsApi.batches,
  })
}

export function useSmsBatch(id: number) {
  return useQuery({
    queryKey: queryKeys.smsBatch(id),
    queryFn: () => smsApi.batch(id),
  })
}

export function useSmsReminder() {
  return useQuery({
    queryKey: queryKeys.smsReminder,
    queryFn: smsApi.reminder,
  })
}

/** Reconciliation is only meaningful once the batch points at an account. */
export function useSmsReconcile(id: number) {
  return useQuery({
    queryKey: queryKeys.smsReconcile(id),
    queryFn: () => smsApi.reconcile(id),
  })
}

/** Read the pasted text and report what was found, storing nothing. */
export function useSmsParsePreview() {
  return useMutation({
    mutationFn: (payload: SmsParsePayload) => smsApi.parsePreview(payload),
  })
}

export function useCreateSmsBatch() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: SmsParsePayload) => smsApi.createBatch(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.smsBatches })
      void queryClient.invalidateQueries({ queryKey: queryKeys.smsReminder })
    },
  })
}

function invalidateSmsBatch(queryClient: ReturnType<typeof useQueryClient>, batchId: number): void {
  void queryClient.invalidateQueries({ queryKey: queryKeys.smsBatch(batchId) })
  void queryClient.invalidateQueries({ queryKey: queryKeys.smsBatches })
  void queryClient.invalidateQueries({ queryKey: queryKeys.smsReconcile(batchId) })
}

export function useUpdateSmsItem(batchId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...payload }: { id: number } & SmsItemPatch) =>
      smsApi.updateItem(id, payload),
    onSuccess: () => {
      invalidateSmsBatch(queryClient, batchId)
      void queryClient.invalidateQueries({ queryKey: queryKeys.smsReminder })
    },
  })
}

export function useBulkUpdateSmsItems(batchId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: SmsBulkPayload) => smsApi.bulkUpdate(payload),
    onSuccess: () => {
      invalidateSmsBatch(queryClient, batchId)
      void queryClient.invalidateQueries({ queryKey: queryKeys.smsReminder })
    },
  })
}

/**
 * Committing is the one SMS action that writes to the ledger, so the whole
 * financial state — balances, budgets, reports — goes stale with it.
 */
export function useCommitSmsBatch(batchId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (itemIds?: number[]) => smsApi.commit(batchId, itemIds),
    onSuccess: () => {
      invalidateFinancialState(queryClient)
      invalidateSmsBatch(queryClient, batchId)
      void queryClient.invalidateQueries({ queryKey: queryKeys.smsReminder })
    },
  })
}

export function useDeleteSmsBatch() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => smsApi.removeBatch(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.smsBatches })
      void queryClient.invalidateQueries({ queryKey: queryKeys.smsReminder })
    },
  })
}

export function useUpdateSmsBatch(batchId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: { note?: string; account?: number | null }) =>
      smsApi.updateBatch(batchId, payload),
    onSuccess: () => invalidateSmsBatch(queryClient, batchId),
  })
}

/** Applying reconciliation rewrites an account's opening balance. */
export function useApplySmsReconcile(batchId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => smsApi.applyReconcile(batchId),
    onSuccess: () => {
      invalidateSmsBatch(queryClient, batchId)
      void queryClient.invalidateQueries({ queryKey: ['accounts'] })
      void queryClient.invalidateQueries({ queryKey: queryKeys.netWorth })
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard })
    },
  })
}

export function useDismissSmsReminder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ year, month }: { year: number; month: number }) =>
      smsApi.dismissReminder(year, month),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.smsReminder })
    },
  })
}

/** The automatic-reading switch and its state, read by the Transactions screen. */
export function useSmsAutoImport() {
  return useQuery({
    queryKey: queryKeys.smsAutoImport,
    queryFn: smsApi.autoImport,
  })
}

/**
 * Turning the switch over.
 *
 * The response *is* the new state, so it is written straight into the cache
 * instead of triggering a refetch: the switch then moves in the same frame the
 * user tapped it, and it can only ever show a value the server confirmed.
 */
export function useSetSmsAutoImport() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (enabled: boolean) => smsApi.setAutoImport(enabled),
    onSuccess: (state) => {
      queryClient.setQueryData(queryKeys.smsAutoImport, state)
    },
  })
}

/**
 * Look for messages that have not been staged yet.
 *
 * Invalidates the batch list and the monthly reminder as well as its own state:
 * a check can stage a batch, and the reminder is derived from whether last
 * month's messages have been dealt with.
 */
export function useSmsSync() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: SmsSyncPayload = {}) => smsApi.sync(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.smsAutoImport })
      void queryClient.invalidateQueries({ queryKey: queryKeys.smsBatches })
      void queryClient.invalidateQueries({ queryKey: queryKeys.smsReminder })
      // Nothing financial is invalidated: a check stages messages for review,
      // and only the review screen writes to the ledger.
    },
  })
}

// ---------------------------------------------------------------------------
// Re-exported types for convenience
// ---------------------------------------------------------------------------

export type {
  Account,
  Asset,
  BudgetAnalysis,
  Dashboard,
  Debt,
  DebtSummary,
  InsightsResponse,
  NetWorth,
  NetWorthPoint,
  Paginated,
  ReportsPayload,
  Transaction,
  TransactionSummary,
}
