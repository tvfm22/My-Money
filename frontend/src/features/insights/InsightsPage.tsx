import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertTriangle,
  CheckCircle2,
  Info,
  Lightbulb,
  Plus,
  Sparkles,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Card } from '../../components/ui/Card'
import { Button } from '../../components/ui/Button'
import { EmptyState } from '../../components/ui/EmptyState'
import { ErrorState } from '../../components/ui/ErrorState'
import { LoadingCard } from '../../components/ui/LoadingState'
import { MonthNavigator } from '../../components/layout/MonthNavigator'
import { useInsights } from '../../hooks/queries'
import { errorMessage } from '../../services/client'
import { formatDigits } from '../../utils/format'
import { currentJalaliMonth } from '../../utils/jalali'
import type { InsightSeverity } from '../../types'

/**
 * Presentation for each severity.
 *
 * Each severity carries an icon and a worded label as well as a colour, so the
 * meaning survives for a user who cannot distinguish the hues.
 */
const SEVERITY: Record<
  InsightSeverity,
  { icon: LucideIcon; label: string; well: string; glyph: string; border: string }
> = {
  attention: {
    icon: AlertTriangle,
    label: 'نیازمند توجه',
    well: 'bg-caution-50',
    glyph: 'text-caution-600',
    border: 'border-caution-100',
  },
  warning: {
    icon: AlertTriangle,
    label: 'هشدار',
    well: 'bg-critical-50',
    glyph: 'text-critical-600',
    border: 'border-critical-100',
  },
  positive: {
    icon: CheckCircle2,
    label: 'نکته مثبت',
    well: 'bg-positive-50',
    glyph: 'text-positive-600',
    border: 'border-positive-100',
  },
  info: {
    icon: Info,
    label: 'اطلاعاتی',
    well: 'bg-info-50',
    glyph: 'text-info-600',
    border: 'border-info-100',
  },
}

type Filter = 'all' | InsightSeverity

/**
 * Financial insights.
 *
 * Every card is derived on the server from recorded transactions, budgets and
 * valuations — the spec is explicit that insights must never be invented. The
 * UI's job is only to present them, grouped by how much attention they deserve.
 */
export function InsightsPage() {
  const today = currentJalaliMonth()
  const [cursor, setCursor] = useState(today)
  const [filter, setFilter] = useState<Filter>('all')

  const { data, isPending, isError, error, refetch, isFetching } = useInsights(
    cursor.year,
    cursor.month,
  )

  const insights = data?.insights ?? []
  const visible = filter === 'all' ? insights : insights.filter((item) => item.severity === filter)
  const counts = data?.counts

  if (isError) {
    return (
      <ErrorState
        message={errorMessage(error, 'بینش‌های مالی دریافت نشد. دوباره تلاش کنید.')}
        onRetry={() => void refetch()}
        isRetrying={isFetching}
      />
    )
  }

  const filters: Array<{ key: Filter; label: string; count: number }> = [
    { key: 'all', label: 'همه', count: insights.length },
    { key: 'attention', label: 'نیازمند توجه', count: counts?.attention ?? 0 },
    { key: 'warning', label: 'هشدار', count: counts?.warning ?? 0 },
    { key: 'positive', label: 'نکته مثبت', count: counts?.positive ?? 0 },
    { key: 'info', label: 'اطلاعاتی', count: counts?.info ?? 0 },
  ] satisfies Array<{ key: Filter; label: string; count: number }>

  const visibleFilters = filters.filter((item) => item.key === 'all' || item.count > 0)

  return (
    <>
      <div className="mb-4">
        <h1 className="text-lg font-bold text-ink lg:text-xl">بینش مالی</h1>
        <p className="mt-1 text-[12.5px] text-ink-soft">
          نکته‌هایی بر پایه داده‌های واقعی ثبت‌شده شما
        </p>
      </div>

      <MonthNavigator
        year={cursor.year}
        month={cursor.month}
        onChange={(year, month) => {
          setCursor({ year, month })
          setFilter('all')
        }}
        className="mb-4"
      />

      {isPending ? (
        <div className="space-y-3">
          <LoadingCard />
          <LoadingCard />
        </div>
      ) : insights.length === 0 ? (
        <Card padded={false}>
          <EmptyState
            icon={<Lightbulb className="size-6" aria-hidden="true" />}
            title="برای این ماه بینشی وجود ندارد"
            description="با ثبت تراکنش‌ها و تعیین بودجه، نکته‌های تحلیلی اینجا نمایش داده می‌شود."
            action={
              <Link to="/transactions">
                <Button size="sm" leadingIcon={<Plus className="size-4" aria-hidden="true" />}>
                  ثبت تراکنش
                </Button>
              </Link>
            }
          />
        </Card>
      ) : (
        <>
          {/* Severity filter */}
          {visibleFilters.length > 2 ? (
            <div className="mb-3 flex flex-wrap gap-2">
              {visibleFilters.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => setFilter(item.key)}
                  aria-pressed={filter === item.key}
                  className={[
                    'flex items-center gap-1.5 rounded-pill border px-3 py-1.5 text-[12px] transition-colors',
                    filter === item.key
                      ? 'border-brand-500 bg-brand-50 font-medium text-brand-700'
                      : 'border-border bg-surface text-ink-soft hover:border-border-strong',
                  ].join(' ')}
                >
                  {item.label}
                  <span className="ltr-nums text-[11px] text-ink-faint">
                    {formatDigits(item.count)}
                  </span>
                </button>
              ))}
            </div>
          ) : null}

          <ul className="space-y-3">
            {visible.map((insight, index) => {
              const style = SEVERITY[insight.severity]
              const Icon = style.icon

              return (
                <li key={`${insight.kind}-${index}`}>
                  <div className={['rounded-card border bg-surface p-4', style.border].join(' ')}>
                    <div className="flex items-start gap-3">
                      <span
                        className={[
                          'flex size-10 shrink-0 items-center justify-center rounded-control',
                          style.well,
                          style.glyph,
                        ].join(' ')}
                      >
                        <Icon className="size-5" aria-hidden="true" />
                      </span>

                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <h2 className="text-[14px] font-semibold text-ink">{insight.title}</h2>
                          <span
                            className={[
                              'rounded-pill px-2 py-0.5 text-[10.5px] font-medium',
                              style.well,
                              style.glyph,
                            ].join(' ')}
                          >
                            {style.label}
                          </span>
                        </div>

                        <p className="mt-1.5 text-[12.5px] leading-6 text-ink-soft">
                          {insight.message}
                        </p>

                        {insight.action ? (
                          <Link
                            to={insight.action}
                            className="mt-2.5 inline-flex items-center gap-1 text-[12px] font-medium text-brand-600 hover:text-brand-700"
                          >
                            مشاهده جزئیات
                          </Link>
                        ) : null}
                      </div>
                    </div>
                  </div>
                </li>
              )
            })}
          </ul>

          {visible.length === 0 ? (
            <Card>
              <p className="py-6 text-center text-[13px] text-ink-faint">
                در این دسته بینشی وجود ندارد.
              </p>
            </Card>
          ) : null}

          {/* Reassurance: these are observations, not advice. */}
          <p className="mt-5 flex items-start gap-2 rounded-control bg-surface-muted px-3 py-2.5 text-[11px] leading-5 text-ink-faint">
            <Sparkles className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
            این نکته‌ها صرفاً بر پایه داده‌های ثبت‌شده شما محاسبه شده‌اند و توصیه مالی یا تضمینی
            برای نتیجه‌گیری نیستند.
          </p>
        </>
      )}
    </>
  )
}
