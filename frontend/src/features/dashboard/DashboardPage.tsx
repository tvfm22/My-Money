import { useState } from 'react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowLeftRight,
  ArrowUpRight,
  BarChart3,
  HandCoins,
  Lightbulb,
  PieChart,
  Plus,
  TrendingDown,
  TrendingUp,
  Wallet,
} from 'lucide-react'
import { Card, CardHeader } from '../../components/ui/Card'
import { Button } from '../../components/ui/Button'
import { EmptyState } from '../../components/ui/EmptyState'
import { ErrorState } from '../../components/ui/ErrorState'
import { LoadingCard, LoadingState } from '../../components/ui/LoadingState'
import { ProgressBar } from '../../components/ui/ProgressBar'
import { MoneyDisplay, MoneyDelta } from '../../components/common/MoneyDisplay'
import { TransactionItem } from '../../components/common/TransactionItem'
import { SpendingTypeSplit } from '../../components/common/SpendingTypeSplit'
import { BudgetProgressCompact } from '../../components/common/BudgetProgress'
import { QuickExpenseSheet } from '../transactions/QuickExpenseSheet'
import { useDashboard } from '../../hooks/queries'
import { useAuth } from '../../hooks/useAuth'
import { errorMessage } from '../../services/client'
import { formatCount } from '../../utils/format'

/**
 * The home screen.
 *
 * Its single job is to answer "وضعیت مالی من الان چطور است؟" within one
 * glance, in this order: how much can I spend, what came in and went out this
 * month, then the budget pace, then the last few transactions.
 */
export function DashboardPage() {
  const { user } = useAuth()
  const [isQuickAddOpen, setIsQuickAddOpen] = useState(false)

  const { data, isPending, isError, error, refetch, isRefetching } = useDashboard()

  if (isError) {
    return (
      <ErrorState
        message={errorMessage(error, 'اطلاعات داشبورد دریافت نشد. دوباره تلاش کنید.')}
        onRetry={() => void refetch()}
        isRetrying={isRefetching}
      />
    )
  }

  return (
    <>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-lg font-bold text-ink lg:text-xl">
            {user?.display_name ? `سلام ${user.display_name}` : 'سلام'}
          </h1>
          <p className="mt-1 text-[12.5px] text-ink-soft">
            {data?.month.label ? `خلاصه مالی ${data.month.label}` : 'خلاصه مالی این ماه'}
          </p>
        </div>
      </div>

      {/* ---------------------------------------------------------------- */}
      {/* Headline: what is actually spendable                              */}
      {/* ---------------------------------------------------------------- */}
      <section aria-label="وضعیت مالی کلی">
        {isPending ? (
          <LoadingCard />
        ) : (
          <Card className="relative overflow-hidden border-brand-100 bg-linear-to-bl from-brand-50 via-surface to-surface">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-[12.5px] text-ink-soft">مانده قابل خرج</p>
                <p className="mt-1.5 text-[28px] leading-tight font-bold tracking-tight text-ink lg:text-[32px]">
                  <MoneyDisplay value={data.summary.spendable} />
                </p>
              </div>
              <span className="flex size-10 shrink-0 items-center justify-center rounded-control bg-brand-100 text-brand-600">
                <Wallet className="size-5" aria-hidden="true" />
              </span>
            </div>

            <p className="mt-2.5 text-[11.5px] leading-5 text-ink-faint">
              جمع موجودی حساب‌ها و درآمد این ماه، منهای هزینه‌ها و اقساط سررسیدشده.
            </p>

            <dl className="mt-4 grid grid-cols-2 gap-3 border-t border-border pt-4 sm:grid-cols-4">
              <div>
                <dt className="text-[11.5px] text-ink-faint">موجودی کل</dt>
                <dd className="mt-1 text-[13.5px] font-semibold text-ink">
                  <MoneyDisplay value={data.summary.balance} compact />
                </dd>
              </div>
              <div>
                <dt className="text-[11.5px] text-ink-faint">ارزش دارایی‌ها</dt>
                <dd className="mt-1 text-[13.5px] font-semibold text-ink">
                  <MoneyDisplay value={data.summary.total_assets} compact />
                </dd>
              </div>
              <div>
                <dt className="text-[11.5px] text-ink-faint">بدهی‌های من</dt>
                <dd className="mt-1 text-[13.5px] font-semibold text-critical-600">
                  <MoneyDisplay value={data.summary.total_debts} compact />
                </dd>
              </div>
              <div>
                <dt className="text-[11.5px] text-ink-faint">طلب‌های من</dt>
                <dd className="mt-1 text-[13.5px] font-semibold text-positive-600">
                  <MoneyDisplay value={data.summary.total_receivables} compact />
                </dd>
              </div>
            </dl>
          </Card>
        )}
      </section>

      {/* ---------------------------------------------------------------- */}
      {/* This month: in vs out                                             */}
      {/* ---------------------------------------------------------------- */}
      <section aria-label="درآمد و هزینه این ماه" className="mt-4">
        {isPending ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <LoadingCard />
            <LoadingCard />
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            <Card>
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-[12.5px] text-ink-soft">درآمد این ماه</p>
                  <p className="mt-1.5 text-xl font-bold text-positive-600">
                    <MoneyDisplay value={data.summary.income} />
                  </p>
                </div>
                <span className="flex size-9 items-center justify-center rounded-control bg-positive-50 text-positive-600">
                  <TrendingUp className="size-4.5" aria-hidden="true" />
                </span>
              </div>
              {data.comparison.income.percent !== null ? (
                <div className="mt-3 border-t border-border pt-3">
                  <MoneyDelta
                    current={data.summary.income}
                    // The server sends the previous month's total directly.
                    // Reconstructing it from the percentage — which this used to
                    // do — round-trips through a rounded number and drifts.
                    previous={data.comparison.income.previous}
                    label={`نسبت به ${data.comparison.previous_month_label}`}
                  />
                </div>
              ) : null}
            </Card>

            <Card>
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-[12.5px] text-ink-soft">هزینه این ماه</p>
                  <p className="mt-1.5 text-xl font-bold text-ink">
                    <MoneyDisplay value={data.summary.expense} />
                  </p>
                </div>
                <span className="flex size-9 items-center justify-center rounded-control bg-surface-muted text-ink-soft">
                  <TrendingDown className="size-4.5" aria-hidden="true" />
                </span>
              </div>
              {data.comparison.expense.percent !== null ? (
                <div className="mt-3 border-t border-border pt-3">
                  <MoneyDelta
                    current={data.summary.expense}
                    previous={data.comparison.expense.previous}
                    label={`نسبت به ${data.comparison.previous_month_label}`}
                  />
                </div>
              ) : null}
            </Card>
          </div>
        )}
      </section>

      {/* ---------------------------------------------------------------- */}
      {/* Where the month's expenses went, by the user's own classification */}
      {/* ---------------------------------------------------------------- */}
      {!isPending && Number(data.spending_types?.total ?? 0) > 0 ? (
        <section aria-label="ترکیب هزینه‌های ماه" className="mt-4">
          <Card>
            <CardHeader
              title="ترکیب هزینه‌ها"
              subtitle="چقدر از هزینه‌های این ماه ضروری، انعطاف‌پذیر یا غیرضروری بوده است"
            />
            <SpendingTypeSplit spendingTypes={data.spending_types} className="mt-4" />
          </Card>
        </section>
      ) : null}

      {/* ---------------------------------------------------------------- */}
      {/* Budget pace                                                       */}
      {/* ---------------------------------------------------------------- */}
      <section aria-label="وضعیت بودجه" className="mt-4">
        {isPending ? (
          <LoadingCard />
        ) : data.budget.has_budget ? (
          <Card>
            <CardHeader
              title="بودجه این ماه"
              subtitle={
                data.month.days_remaining > 0 ? (
                  <>
                    <span className="ltr-nums">{formatCount(data.month.days_remaining)}</span> روز
                    تا پایان ماه باقی مانده
                  </>
                ) : (
                  'ماه در حال پایان است'
                )
              }
              action={
                <Link
                  to="/budgets"
                  className="text-xs font-medium text-brand-600 hover:text-brand-700"
                >
                  جزئیات
                </Link>
              }
            />

            <div className="mt-4 space-y-3">
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-[13px] text-ink-soft">
                  <span className="ltr-nums font-semibold text-ink">
                    {data.budget.totals.spent_display}
                  </span>
                  {' از '}
                  <span className="ltr-nums">{data.budget.totals.budgeted_display}</span>
                </span>
                <span className="ltr-nums text-[13px] font-semibold text-ink">
                  {data.budget.totals.consumed_display}
                </span>
              </div>

              <ProgressBar
                value={Number(data.budget.totals.consumed_percent || 0)}
                tone={
                  Number(data.budget.totals.consumed_percent) > 100
                    ? 'critical'
                    : Number(data.budget.totals.consumed_percent) >= 80
                      ? 'caution'
                      : 'positive'
                }
                size="lg"
                markerPercent={Number(data.month.elapsed_percent || 0)}
                label="میزان مصرف کل بودجه این ماه"
              />

              <div className="flex items-center justify-between text-[11.5px] text-ink-faint">
                <span>
                  {'مصرف‌شده '}
                  <span className="ltr-nums">{data.budget.totals.consumed_display}</span>
                </span>
                <span>
                  {'گذشت ماه '}
                  <span className="ltr-nums">{data.month.elapsed_display}</span>
                </span>
              </div>
            </div>

            {data.budget.top_categories.length > 0 ? (
              <div className="mt-5 space-y-4 border-t border-border pt-4">
                <p className="text-[12.5px] font-medium text-ink-soft">
                  بیشترین مصرف در دسته‌ها
                </p>
                {data.budget.top_categories.slice(0, 4).map((item) => (
                  <BudgetProgressCompact
                    key={item.category_id}
                    name={item.category_name}
                    icon={item.category_icon}
                    color={item.category_color}
                    spentDisplay={item.spent_display}
                    consumedPercent={item.consumed_percent}
                    status={item.status}
                    statusLabel={item.status_label}
                    elapsedPercent={data.month.elapsed_percent}
                  />
                ))}
              </div>
            ) : null}
          </Card>
        ) : (
          <Card padded={false}>
            <EmptyState
              icon={<PieChart className="size-6" aria-hidden="true" />}
              title="برای این ماه بودجه‌ای تعیین نشده"
              description="با تعیین بودجه، می‌توانید سرعت مصرف هر دسته را در طول ماه ببینید."
              action={
                <Link to="/budgets">
                  <Button size="sm">تعیین بودجه ماه</Button>
                </Link>
              }
            />
          </Card>
        )}
      </section>

      {/* ---------------------------------------------------------------- */}
      {/* Recent transactions                                               */}
      {/* ---------------------------------------------------------------- */}
      <section aria-label="تراکنش‌های اخیر" className="mt-4">
        <Card padded={false}>
          <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3.5 sm:px-5">
            <h2 className="text-[15px] font-semibold text-ink">تراکنش‌های اخیر</h2>
            <Link
              to="/transactions"
              className="text-xs font-medium text-brand-600 hover:text-brand-700"
            >
              همه تراکنش‌ها
            </Link>
          </div>

          {isPending ? (
            <div className="p-4">
              <LoadingState rows={3} />
            </div>
          ) : data.recent_transactions.length === 0 ? (
            <EmptyState
              icon={<ArrowLeftRight className="size-6" aria-hidden="true" />}
              title="هنوز تراکنشی ثبت نکرده‌اید"
              description="اولین هزینه یا درآمد خود را ثبت کنید تا تحلیل‌ها شروع شود."
              action={
                <Button
                  size="sm"
                  onClick={() => setIsQuickAddOpen(true)}
                  leadingIcon={<Plus className="size-4" aria-hidden="true" />}
                >
                  ثبت تراکنش
                </Button>
              }
            />
          ) : (
            <ul className="divide-y divide-border">
              {data.recent_transactions.slice(0, 7).map((transaction) => (
                <li key={transaction.id} className="p-2.5 sm:p-3">
                  <TransactionItem transaction={transaction} showAccount />
                </li>
              ))}
            </ul>
          )}
        </Card>
      </section>

      {/* ---------------------------------------------------------------- */}
      {/* Shortcuts                                                         */}
      {/* ---------------------------------------------------------------- */}
      <section aria-label="دسترسی سریع" className="mt-4">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <ShortcutCard to="/debts" icon={<HandCoins className="size-4.5" />} label="بدهی‌ها و طلب‌ها" />
          <ShortcutCard to="/assets" icon={<Wallet className="size-4.5" />} label="دارایی‌ها" />
          <ShortcutCard to="/reports" icon={<BarChart3 className="size-4.5" />} label="گزارش‌ها" />
          <ShortcutCard to="/insights" icon={<Lightbulb className="size-4.5" />} label="بینش مالی" />
        </div>
      </section>

      {/* A neutral "this month" footnote rather than a hidden state. */}
      {!isPending && data.summary.transactions_count > 0 ? (
        <p className="mt-5 text-center text-[11px] text-ink-faint">
          <span className="ltr-nums">{formatCount(data.summary.transactions_count)}</span> تراکنش
          در {data.month.label} ثبت شده است.
        </p>
      ) : null}

      <QuickExpenseSheet open={isQuickAddOpen} onClose={() => setIsQuickAddOpen(false)} />
    </>
  )
}

// ---------------------------------------------------------------------------

function ShortcutCard({
  to,
  icon,
  label,
}: {
  to: string
  icon: ReactNode
  label: string
}) {
  return (
    <Link
      to={to}
      className="flex items-center gap-2.5 rounded-card border border-border bg-surface p-3.5 transition-all active:scale-[0.98] hover:shadow-raised"
    >
      <span className="flex size-9 shrink-0 items-center justify-center rounded-control bg-surface-muted text-ink-soft">
        {icon}
      </span>
      <span className="min-w-0 flex-1 truncate text-[12.5px] font-medium text-ink">{label}</span>
      <ArrowUpRight className="size-3.5 shrink-0 text-ink-faint" aria-hidden="true" />
    </Link>
  )
}
