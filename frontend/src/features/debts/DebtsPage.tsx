import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { HandCoins, Plus, TrendingDown, TrendingUp } from 'lucide-react'
import { Card, CardHeader } from '../../components/ui/Card'
import { Button } from '../../components/ui/Button'
import { Badge } from '../../components/ui/Badge'
import { EmptyState } from '../../components/ui/EmptyState'
import { ErrorState } from '../../components/ui/ErrorState'
import { LoadingState } from '../../components/ui/LoadingState'
import { MoneyDisplay } from '../../components/common/MoneyDisplay'
import { DebtForm } from './DebtForm'
import { useDebtSummary, useDebts } from '../../hooks/queries'
import { errorMessage } from '../../services/client'
import { formatPercent, formatDigits } from '../../utils/format'
import type { Debt, DebtStatusValue } from '../../types'

type Direction = 'payable' | 'receivable'

const STATUS_VARIANT: Record<DebtStatusValue, 'positive' | 'info' | 'caution' | 'critical' | 'neutral'> = {
  active: 'info',
  partial: 'caution',
  settled: 'positive',
  overdue: 'critical',
}

/**
 * Debts and receivables.
 *
 * The two directions are separated into tabs because they answer different
 * questions — "چه بدهی دارم؟" versus "چه طلبی دارم؟" — and mixing them into
 * one list makes both harder to read.
 */
export function DebtsPage() {
  const [direction, setDirection] = useState<Direction>('payable')
  const [isFormOpen, setIsFormOpen] = useState(false)
  const [editing, setEditing] = useState<Debt | null>(null)

  const { data: summary, isPending: isSummaryPending } = useDebtSummary()
  const { data, isPending, isError, error, refetch, isFetching } = useDebts({ direction })

  const items = data?.results ?? []

  const openCreate = () => {
    setEditing(null)
    setIsFormOpen(true)
  }

  const openEdit = (debt: Debt) => {
    setEditing(debt)
    setIsFormOpen(true)
  }

  // Overdue items float to the top of the payable list — those are the ones
  // that need attention.
  const ordered = useMemo(() => {
    return [...items].sort((a, b) => {
      if (a.is_overdue !== b.is_overdue) return a.is_overdue ? -1 : 1
      if (a.is_settled !== b.is_settled) return a.is_settled ? 1 : -1
      const aDays = a.days_until_due ?? Number.MAX_SAFE_INTEGER
      const bDays = b.days_until_due ?? Number.MAX_SAFE_INTEGER
      return aDays - bDays
    })
  }, [items])

  return (
    <>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-bold text-ink lg:text-xl">بدهی‌ها و طلب‌ها</h1>
          <p className="mt-1 text-[12.5px] text-ink-soft">
            پیگیری اقساط، وام‌ها و پول‌هایی که به دیگران داده‌اید
          </p>
        </div>

        <Button
          size="sm"
          onClick={openCreate}
          leadingIcon={<Plus className="size-4" aria-hidden="true" />}
          className="shrink-0"
        >
          ثبت
        </Button>
      </div>

      {/* Net position summary */}
      {!isSummaryPending && summary ? (
        <Card className="mb-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <p className="flex items-center gap-1.5 text-[11.5px] text-ink-faint">
                <TrendingDown className="size-3.5" aria-hidden="true" />
                بدهی‌های من
              </p>
              <p className="mt-1.5 text-[17px] font-bold text-critical-600">
                <MoneyDisplay value={summary.payable_remaining} />
              </p>
              <p className="mt-0.5 text-[11px] text-ink-faint">
                از مجموع <span className="ltr-nums">{summary.payable_total_display}</span>
              </p>
            </div>

            <div className="sm:border-x sm:border-border sm:px-4">
              <p className="flex items-center gap-1.5 text-[11.5px] text-ink-faint">
                <TrendingUp className="size-3.5" aria-hidden="true" />
                طلب‌های من
              </p>
              <p className="mt-1.5 text-[17px] font-bold text-positive-600">
                <MoneyDisplay value={summary.receivable_remaining} />
              </p>
              <p className="mt-0.5 text-[11px] text-ink-faint">
                از مجموع <span className="ltr-nums">{summary.receivable_total_display}</span>
              </p>
            </div>

            <div>
              <p className="text-[11.5px] text-ink-faint">وضعیت خالص</p>
              <p className="mt-1.5 text-[17px] font-bold text-ink">
                <MoneyDisplay value={summary.net_position} signed coloured invertColour />
              </p>
              <p className="mt-0.5 text-[11px] text-ink-faint">
                طلب منهای بدهی
              </p>
            </div>
          </div>

          {summary.overdue_count > 0 ? (
            <div className="mt-4 rounded-control bg-critical-50 px-3 py-2.5">
              <p className="text-[12px] font-medium text-critical-700">
                <span className="ltr-nums">{formatDigits(summary.overdue_count)}</span>
                {' مورد سررسید گذشته، به مبلغ '}
                <span className="ltr-nums">{summary.overdue_amount_display}</span>
              </p>
            </div>
          ) : null}
        </Card>
      ) : isSummaryPending ? (
        <Card className="mb-4">
          <div className="grid gap-4 sm:grid-cols-3">
            {[0, 1, 2].map((index) => (
              <div key={index} className="space-y-2">
                <div className="skeleton h-3 w-20 rounded-full" />
                <div className="skeleton h-5 w-32 rounded-lg" />
              </div>
            ))}
          </div>
        </Card>
      ) : null}

      {/* Direction tabs */}
      <div className="mb-3 grid grid-cols-2 gap-1 rounded-control bg-surface-muted p-1">
        {(['payable', 'receivable'] as const).map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => setDirection(option)}
            aria-pressed={direction === option}
            className={[
              'h-10 rounded-control text-[13px] font-medium transition-colors',
              direction === option ? 'bg-surface text-ink shadow-card' : 'text-ink-soft hover:text-ink',
            ].join(' ')}
          >
            {option === 'payable' ? 'بدهی‌های من' : 'طلب‌های من'}
          </button>
        ))}
      </div>

      {/* List */}
      {isError ? (
        <ErrorState
          compact
          message={errorMessage(error, 'فهرست بدهی‌ها دریافت نشد.')}
          onRetry={() => void refetch()}
          isRetrying={isFetching}
        />
      ) : isPending ? (
        <LoadingState rows={3} />
      ) : ordered.length === 0 ? (
        <Card padded={false}>
          <EmptyState
            icon={<HandCoins className="size-6" aria-hidden="true" />}
            title={
              direction === 'payable'
                ? 'بدهی‌ای ثبت نشده است'
                : 'طلبی ثبت نشده است'
            }
            description={
              direction === 'payable'
                ? 'وام‌ها، اقساط و پول‌هایی که باید بپردازید را اینجا ثبت کنید تا سررسیدها را از دست ندهید.'
                : 'اگر به کسی پول قرض داده‌اید، آن را ثبت کنید تا بازپرداخت‌ها را پیگیری کنید.'
            }
            action={
              <Button size="sm" onClick={openCreate}>
                ثبت {direction === 'payable' ? 'بدهی' : 'طلب'}
              </Button>
            }
          />
        </Card>
      ) : (
        <ul className="space-y-2.5">
          {ordered.map((debt) => (
            <li key={debt.id}>
              <DebtCard debt={debt} onClick={() => openEdit(debt)} />
            </li>
          ))}
        </ul>
      )}

      {summary && summary.upcoming.length > 0 && direction === 'payable' ? (
        <Card className="mt-4">
          <CardHeader title="سررسیدهای نزدیک" subtitle="در روزهای آینده" />
          <ul className="mt-3 divide-y divide-border">
            {summary.upcoming.slice(0, 5).map((debt) => (
              <li key={debt.id} className="flex items-center justify-between gap-3 py-2.5">
                <div className="min-w-0">
                  <p className="truncate text-[13px] font-medium text-ink">{debt.counterparty}</p>
                  <p className="mt-0.5 text-[11px] text-ink-faint">
                    {debt.due_on_display}
                    {debt.due_relative ? ` • ${debt.due_relative}` : ''}
                  </p>
                </div>
                <span className="ltr-nums shrink-0 text-[13px] font-semibold text-ink">
                  {debt.remaining_display}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      <DebtForm
        open={isFormOpen}
        debt={editing}
        defaultDirection={direction}
        onClose={() => {
          setIsFormOpen(false)
          setEditing(null)
        }}
      />
    </>
  )
}

// ---------------------------------------------------------------------------

function DebtCard({ debt, onClick }: { debt: Debt; onClick: () => void }) {
  const paidPercent = Number(debt.paid_percent || 0)

  return (
    <div className="rounded-card border border-border bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-[14px] font-semibold text-ink">{debt.counterparty}</h3>
            <Badge variant={STATUS_VARIANT[debt.status]} size="sm">
              {debt.status_label}
            </Badge>
          </div>

          {debt.description ? (
            <p className="mt-1 line-clamp-2 text-[11.5px] leading-5 text-ink-faint">
              {debt.description}
            </p>
          ) : null}
        </div>

        <div className="shrink-0 text-end">
          <p className="ltr-nums text-[14px] font-bold text-ink">{debt.remaining_display}</p>
          <p className="mt-0.5 text-[10.5px] text-ink-faint">باقی‌مانده</p>
        </div>
      </div>

      {/* Progress: how much of the principal has been settled */}
      <div className="mt-3.5">
        <div className="mb-1.5 flex items-center justify-between text-[11px] text-ink-faint">
          <span>
            {'پرداخت‌شده '}
            <span className="ltr-nums">{debt.paid_display}</span>
            {' از '}
            <span className="ltr-nums">{debt.principal_display}</span>
          </span>
          <span className="ltr-nums">{formatPercent(paidPercent)}</span>
        </div>

        <div
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(Math.min(100, paidPercent))}
          aria-label={`میزان پرداخت ${debt.counterparty}`}
          className="h-2 w-full overflow-hidden rounded-pill bg-surface-muted"
        >
          <div
            className={[
              'h-full rounded-pill transition-[width] duration-300',
              debt.is_overdue ? 'bg-critical-500' : debt.is_settled ? 'bg-positive-500' : 'bg-brand-500',
            ].join(' ')}
            style={{ width: `${Math.min(100, paidPercent)}%` }}
          />
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between gap-3 border-t border-border pt-3">
        <span className="text-[11px] text-ink-faint">
          {debt.is_settled ? (
            'تسویه شده'
          ) : (
            <>
              {'سررسید: '}
              <span className="text-ink-soft">{debt.due_on_display}</span>
              {debt.due_relative && !debt.is_overdue ? ` • ${debt.due_relative}` : ''}
              {debt.is_overdue ? (
                <span className="font-medium text-critical-600"> • سررسید گذشته</span>
              ) : null}
            </>
          )}
        </span>

        <div className="flex shrink-0 gap-2">
          <Link
            to={`/debts/${debt.id}`}
            className="text-[12px] font-medium text-brand-600 hover:text-brand-700"
          >
            جزئیات
          </Link>
          <button
            type="button"
            onClick={onClick}
            className="text-[12px] font-medium text-ink-soft hover:text-ink"
          >
            ویرایش
          </button>
        </div>
      </div>
    </div>
  )
}
