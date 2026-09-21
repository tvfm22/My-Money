import { ArrowLeftRight } from 'lucide-react'
import { ResponsiveDialog } from '../../components/ui/ResponsiveDialog'
import { Button } from '../../components/ui/Button'
import { EmptyState } from '../../components/ui/EmptyState'
import { LoadingState } from '../../components/ui/LoadingState'
import { TransactionItem } from '../../components/common/TransactionItem'
import { MoneyDisplay } from '../../components/common/MoneyDisplay'
import { CategoryIcon } from '../../components/common/CategoryIcon'
import { useTransactionSummary, useTransactions } from '../../hooks/queries'
import type { TransactionFilters } from '../../types'

export interface CategoryDrillDownProps {
  open: boolean
  onClose: () => void
  /** Only render this component while a category is actually selected. */
  categoryId: number
  name: string
  icon: string
  color: string
  /** Jalali year/month the budget page is currently showing. */
  year: number
  month: number
}

/**
 * The month's itemised expenses for one budgeted category.
 *
 * Opened by tapping a category card on the budgets page. The same list and
 * summary endpoints power the transactions ledger — this view only narrows
 * them to a single category and the month on screen.
 */
export function CategoryDrillDown({
  open,
  onClose,
  categoryId,
  name,
  icon,
  color,
  year,
  month,
}: CategoryDrillDownProps) {
  const filters: TransactionFilters = {
    category: categoryId,
    transaction_type: 'expense',
    month: `${year}-${String(month).padStart(2, '0')}`,
  }

  const { data: pages, isPending, isFetchingNextPage, hasNextPage, fetchNextPage } =
    useTransactions(filters)
  const { data: summary } = useTransactionSummary(filters)

  const rows = (pages?.pages ?? []).flatMap((page) => page.results)
  const total = summary?.expense_total ?? null
  const count = summary?.count ?? 0

  return (
    <ResponsiveDialog
      open={open}
      onClose={onClose}
      title={name}
      description={`ریز هزینه‌های ثبت‌شده برای «${name}» در این ماه`}
      size="lg"
      footer={
        <div className="flex items-center justify-between gap-3">
          <span className="text-[12.5px] text-ink-soft">
            {'جمع هزینه این دسته: '}
            {total !== null ? (
              <span className="ltr-nums font-semibold text-ink">
                <MoneyDisplay value={total} compact />
              </span>
            ) : (
              '—'
            )}
          </span>
          <Button variant="secondary" size="sm" onClick={onClose}>
            بستن
          </Button>
        </div>
      }
    >
      <div className="space-y-3">
        <div className="flex items-center gap-2.5 rounded-control bg-surface-muted px-3 py-2.5">
          <CategoryIcon name={icon} color={color} size="sm" />
          <span className="min-w-0 flex-1 truncate text-[12.5px] text-ink-soft">
            {count > 0 ? (
              <>
                <span className="ltr-nums">{count}</span> تراکنش هزینه در این ماه
              </>
            ) : (
              'هزینه‌ای برای این دسته در ماه جاری یافت نشد'
            )}
          </span>
        </div>

        {isPending ? (
          <LoadingState rows={4} />
        ) : rows.length === 0 ? (
          <EmptyState
            icon={<ArrowLeftRight className="size-6" aria-hidden="true" />}
            title="هزینه‌ای ثبت نشده است"
            description="هنوز هزینه‌ای با این دسته‌بندی در این ماه ثبت نشده است."
          />
        ) : (
          <ul className="space-y-2">
            {rows.map((transaction) => (
              <li key={transaction.id}>
                <TransactionItem transaction={transaction} />
              </li>
            ))}
          </ul>
        )}

        {hasNextPage ? (
          <Button
            variant="secondary"
            className="w-full"
            isLoading={isFetchingNextPage}
            onClick={() => void fetchNextPage()}
          >
            نمایش بیشتر
          </Button>
        ) : null}
      </div>
    </ResponsiveDialog>
  )
}
