import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Filter, Plus, Search, SlidersHorizontal, X } from 'lucide-react'
import { Card } from '../../components/ui/Card'
import { Button } from '../../components/ui/Button'
import { useToast } from '../../components/ui/Toast'
import { Input } from '../../components/ui/Input'
import { Select } from '../../components/ui/Select'
import { EmptyState } from '../../components/ui/EmptyState'
import { ErrorState } from '../../components/ui/ErrorState'
import { LoadingState } from '../../components/ui/LoadingState'
import { Skeleton } from '../../components/ui/Skeleton'
import { TransactionItem } from '../../components/common/TransactionItem'
import { MoneyDisplay } from '../../components/common/MoneyDisplay'
import { QuickExpenseSheet } from './QuickExpenseSheet'
import { TransactionForm } from './TransactionForm'
import { SmsAutoImportCard } from '../sms/SmsAutoImportCard'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import {
  useAccounts,
  useCategoryPicker,
  useCreateTransaction,
  useDeleteTransaction,
  useTransactionSummary,
  useTransactions,
} from '../../hooks/queries'
import { errorMessage } from '../../services/client'
import { formatCount } from '../../utils/format'
import { currentJalaliMonth, formatRelativeDay, jalaliMonthBounds } from '../../utils/jalali'
import type { Transaction, TransactionFilters, TransactionType } from '../../types'

type TypeFilter = 'all' | TransactionType

/**
 * The transaction ledger.
 *
 * On phones this renders as a date-grouped card list, not a table — the spec
 * is explicit that wide tables are not acceptable on mobile. The filter row
 * scrolls horizontally so it never wraps into three rows of chips.
 */
export function TransactionsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('all')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [accountFilter, setAccountFilter] = useState('')
  const [period, setPeriod] = useState<'this_month' | 'last_month' | 'all'>('this_month')
  const [ordering, setOrdering] = useState('-occurred_on')
  const [showFilters, setShowFilters] = useState(false)

  const [isQuickAddOpen, setIsQuickAddOpen] = useState(false)
  const [editing, setEditing] = useState<Transaction | null>(null)

  // The app shell's search icon deep-links here with ?focus=search; the
  // transaction list must actually receive that focus, and the parameter is
  // then cleared so a refresh does not re-steal focus.
  const searchInputRef = useRef<HTMLInputElement>(null)
  const shouldFocusSearch = searchParams.get('focus') === 'search'
  useEffect(() => {
    if (!shouldFocusSearch) return
    searchInputRef.current?.focus()
    setSearchParams({}, { replace: true })
  }, [shouldFocusSearch, setSearchParams])

  // One request per pause in typing, not per keystroke.
  const debouncedSearch = useDebouncedValue(search, 300)

  const filters = useMemo<TransactionFilters>(() => {
    const base: TransactionFilters = {
      ordering,
      page_size: 25,
    }

    if (debouncedSearch.trim()) base.search = debouncedSearch.trim()
    if (typeFilter !== 'all') base.transaction_type = typeFilter
    if (categoryFilter) base.category = Number(categoryFilter)
    if (accountFilter) base.account = Number(accountFilter)

    if (period !== 'all') {
      const today = currentJalaliMonth()
      const target =
        period === 'this_month'
          ? today
          : today.month === 1
            ? { year: today.year - 1, month: 12 }
            : { year: today.year, month: today.month - 1 }

      const bounds = jalaliMonthBounds(target.year, target.month)
      base.date_from = bounds.from
      base.date_to = bounds.to
    }

    return base
  }, [debouncedSearch, typeFilter, categoryFilter, accountFilter, period, ordering])

  const {
    data,
    isPending,
    isError,
    error,
    refetch,
    isFetching,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useTransactions(filters)
  const { data: summary } = useTransactionSummary(filters)
  const { data: categories } = useCategoryPicker()
  const { data: accounts } = useAccounts()
  const deleteTransaction = useDeleteTransaction()
  const createTransaction = useCreateTransaction()
  const { showToast } = useToast()

  /**
   * Deletes a transaction and offers a short window to undo.
   *
   * Undo re-creates the row from the fields it carried (a new id, but the
   * same money) rather than standing between the user and the delete with a
   * dialog — the destructive action happens immediately, and the reversal is
   * one tap away while the toast is visible.
   */
  const handleDelete = (id: number) => {
    const target = allTransactions.find((transaction) => transaction.id === id)
    deleteTransaction.mutate(id, {
      onSuccess: () => {
        if (!target) return
        showToast({
          message: 'تراکنش حذف شد.',
          action: {
            label: 'بازگردانی',
            onClick: () =>
              createTransaction.mutate({
                transaction_type: target.transaction_type,
                amount: target.amount,
                category: target.category,
                account: target.account,
                occurred_on: target.occurred_on,
                description: target.description ?? '',
              }),
          },
        })
      },
    })
  }

  const activeFilterCount = [
    typeFilter !== 'all',
    Boolean(categoryFilter),
    Boolean(accountFilter),
    period !== 'this_month',
  ].filter(Boolean).length

  const resetFilters = () => {
    setTypeFilter('all')
    setCategoryFilter('')
    setAccountFilter('')
    setPeriod('this_month')
  }

  // Group by day so the list reads like a statement. The API returns them
  // already ordered within each page and pages arrive in order, so
  // concatenation preserves the ordering across the whole loaded range.
  const allTransactions = useMemo(
    () => data?.pages.flatMap((page) => page.results) ?? [],
    [data?.pages],
  )

  const grouped = useMemo(() => {
    const groups = new Map<string, Transaction[]>()
    for (const transaction of allTransactions) {
      const key = transaction.occurred_on
      const bucket = groups.get(key)
      if (bucket) bucket.push(transaction)
      else groups.set(key, [transaction])
    }
    return Array.from(groups.entries())
  }, [allTransactions])

  const categoryOptions = useMemo(
    () => (categories ?? []).map((c) => ({ value: String(c.id), label: c.name })),
    [categories],
  )

  const accountOptions = useMemo(
    () => (accounts?.results ?? []).map((a) => ({ value: String(a.id), label: a.name })),
    [accounts],
  )

  return (
    <>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-bold text-ink lg:text-xl">تراکنش‌ها</h1>
          <p className="mt-1 text-[12.5px] text-ink-soft">
            {summary
              ? `${formatCount(summary.count)} تراکنش در این بازه`
              : 'درآمدها و هزینه‌های خود را مدیریت کنید'}
          </p>
        </div>

        <Button
          size="sm"
          onClick={() => setIsQuickAddOpen(true)}
          leadingIcon={<Plus className="size-4" aria-hidden="true" />}
          className="shrink-0"
        >
          ثبت تراکنش
        </Button>
      </div>

      {/* Bank messages sit above the ledger: the transactions they produce land
          in the list below, and reading them is something done *while looking
          at* the ledger rather than on a screen of its own. */}
      <SmsAutoImportCard />

      {/* Search + filter toggle */}
      <div className="mb-3 flex gap-2">
        <Input
          ref={searchInputRef}
          containerClassName="flex-1"
          placeholder="جست‌وجو در توضیحات…"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          leadingIcon={<Search className="size-4" aria-hidden="true" />}
          trailingSlot={
            search ? (
              <button
                type="button"
                onClick={() => setSearch('')}
                aria-label="پاک کردن جست‌وجو"
                className="flex size-11 items-center justify-center rounded-control text-ink-faint transition-colors hover:bg-surface-muted active:bg-surface-muted"
              >
                <X className="size-3.5" aria-hidden="true" />
              </button>
            ) : undefined
          }
        />

        <button
          type="button"
          onClick={() => setShowFilters((current) => !current)}
          aria-expanded={showFilters}
          className={[
            'relative flex h-11 shrink-0 items-center gap-2 rounded-control border px-3 text-[13px] font-medium transition-colors',
            showFilters || activeFilterCount > 0
              ? 'border-brand-300 bg-brand-50 text-brand-700'
              : 'border-border-strong bg-surface text-ink-soft hover:bg-surface-muted',
          ].join(' ')}
        >
          <SlidersHorizontal className="size-4" aria-hidden="true" />
          <span className="hidden sm:inline">فیلترها</span>
          {activeFilterCount > 0 ? (
            <span className="ltr-nums flex size-5 items-center justify-center rounded-pill bg-brand-600 text-[10px] text-white">
              {activeFilterCount}
            </span>
          ) : null}
        </button>
      </div>

      {/* Filter panel */}
      {showFilters ? (
        <Card className="mb-3 animate-fade-rise">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Select
              label="نوع"
              value={typeFilter}
              onChange={(event) => setTypeFilter(event.target.value as TypeFilter)}
              options={[
                { value: 'all', label: 'همه' },
                { value: 'expense', label: 'هزینه' },
                { value: 'income', label: 'درآمد' },
              ]}
            />

            <Select
              label="دسته‌بندی"
              value={categoryFilter}
              onChange={(event) => setCategoryFilter(event.target.value)}
              placeholder="همه دسته‌ها"
              options={categoryOptions}
            />

            <Select
              label="حساب"
              value={accountFilter}
              onChange={(event) => setAccountFilter(event.target.value)}
              placeholder="همه حساب‌ها"
              options={accountOptions}
            />

            <Select
              label="بازه زمانی"
              value={period}
              onChange={(event) => setPeriod(event.target.value as typeof period)}
              options={[
                { value: 'this_month', label: 'این ماه' },
                { value: 'last_month', label: 'ماه گذشته' },
                { value: 'all', label: 'همه' },
              ]}
            />
          </div>

          <div className="mt-3 flex items-center justify-between gap-3 border-t border-border pt-3">
            <Select
              containerClassName="w-40"
              value={ordering}
              onChange={(event) => setOrdering(event.target.value)}
              options={[
                { value: '-occurred_on', label: 'جدیدترین' },
                { value: 'occurred_on', label: 'قدیمی‌ترین' },
                { value: '-amount', label: 'بیشترین مبلغ' },
                { value: 'amount', label: 'کمترین مبلغ' },
              ]}
            />

            {activeFilterCount > 0 ? (
              <Button
                variant="ghost"
                size="sm"
                onClick={resetFilters}
                leadingIcon={<Filter className="size-3.5" aria-hidden="true" />}
              >
                حذف فیلترها
              </Button>
            ) : null}
          </div>
        </Card>
      ) : null}

      {/* Summary strip for the current filter set */}
      {summary && !isPending ? (
        <div className="mb-3 grid grid-cols-3 gap-2 rounded-card border border-border bg-surface p-3">
          <div className="text-center">
            <p className="text-[11px] text-ink-faint">درآمد</p>
            <p className="mt-0.5 text-[13px] font-semibold text-positive-600">
              <MoneyDisplay value={summary.income_total} compact />
            </p>
          </div>
          <div className="border-x border-border text-center">
            <p className="text-[11px] text-ink-faint">هزینه</p>
            <p className="mt-0.5 text-[13px] font-semibold text-ink">
              <MoneyDisplay value={summary.expense_total} compact />
            </p>
          </div>
          <div className="text-center">
            <p className="text-[11px] text-ink-faint">مانده</p>
            <p className="mt-0.5 text-[13px] font-semibold text-ink">
              <MoneyDisplay value={summary.net} compact coloured signed />
            </p>
          </div>
        </div>
      ) : null}

      {/* The list */}
      {isError ? (
        <ErrorState
          compact
          message={errorMessage(error, 'فهرست تراکنش‌ها دریافت نشد.')}
          onRetry={() => void refetch()}
          isRetrying={isFetching}
        />
      ) : isPending ? (
        <TransactionListSkeleton />
      ) : grouped.length === 0 ? (
        <Card padded={false}>
          <EmptyState
            title={
              search || activeFilterCount > 0
                ? 'تراکنشی با این فیلترها پیدا نشد'
                : 'هنوز تراکنشی ثبت نکرده‌اید'
            }
            description={
              search || activeFilterCount > 0
                ? 'بازه زمانی یا دسته‌بندی را تغییر دهید.'
                : 'با ثبت اولین تراکنش، تحلیل‌های مالی شما شروع می‌شود.'
            }
            action={
              search || activeFilterCount > 0 ? (
                <Button variant="secondary" size="sm" onClick={resetFilters}>
                  حذف فیلترها
                </Button>
              ) : (
                <Button size="sm" onClick={() => setIsQuickAddOpen(true)}>
                  ثبت تراکنش
                </Button>
              )
            }
          />
        </Card>
      ) : (
        <div className="space-y-4">
          {grouped.map(([isoDate, items]) => (
            <section key={isoDate}>
              <div className="mb-2 flex items-center justify-between px-1">
                <h2 className="text-[12.5px] font-semibold text-ink-soft">
                  {formatRelativeDay(isoDate)}
                </h2>
                <span className="ltr-nums text-[11px] text-ink-faint">
                  {formatCount(items.length)} مورد
                </span>
              </div>

              <ul className="space-y-1.5">
                {items.map((transaction) => (
                  <li key={transaction.id}>
                    <TransactionItem
                      transaction={transaction}
                      showAccount
                      onClick={setEditing}
                    />
                  </li>
                ))}
              </ul>
            </section>
          ))}

          {/* Pagination is intentionally simple: a "load more" rather than
              numbered pages, which is far easier to hit with a thumb. The
              infinite query *appends* the next page to what is already on
              screen — the loaded list is never replaced. */}
          {hasNextPage ? (
            <div className="pt-1">
              <Button
                variant="secondary"
                fullWidth
                onClick={() => void fetchNextPage()}
                isLoading={isFetchingNextPage}
              >
                نمایش تراکنش‌های بیشتر
              </Button>
            </div>
          ) : (
            <p className="pt-2 text-center text-[11px] text-ink-faint">
              به پایان فهرست رسیدید.
            </p>
          )}
        </div>
      )}

      <QuickExpenseSheet open={isQuickAddOpen} onClose={() => setIsQuickAddOpen(false)} />

      <TransactionForm
        open={editing !== null}
        transaction={editing}
        onClose={() => setEditing(null)}
        onDelete={handleDelete}
        isDeleting={deleteTransaction.isPending}
      />
    </>
  )
}

// ---------------------------------------------------------------------------

function TransactionListSkeleton() {
  return (
    <div className="space-y-4" role="status" aria-busy="true">
      <span className="sr-only">در حال بارگذاری تراکنش‌ها…</span>
      {[0, 1].map((group) => (
        <div key={group}>
          <Skeleton className="mb-2 h-3.5 w-24 rounded-full" />
          <LoadingState rows={3} />
        </div>
      ))}
    </div>
  )
}
