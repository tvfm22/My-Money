import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Info } from 'lucide-react'
import { Card, CardHeader } from '../../components/ui/Card'
import { EmptyState } from '../../components/ui/EmptyState'
import { ErrorState } from '../../components/ui/ErrorState'
import { LoadingCard } from '../../components/ui/LoadingState'
import { BudgetProgress } from '../../components/common/BudgetProgress'
import { MonthNavigator } from '../../components/layout/MonthNavigator'
import { useBudgetPerformance } from '../../hooks/queries'
import { errorMessage } from '../../services/client'
import { formatDigits } from '../../utils/format'
import { currentJalaliMonth } from '../../utils/jalali'
import type { BudgetStatus } from '../../types'

type Bucket = BudgetStatus | 'all'

const BUCKETS: Array<{ key: Bucket; label: string; variant: 'positive' | 'info' | 'caution' | 'critical' | 'neutral' }> = [
  { key: 'all', label: 'همه', variant: 'neutral' },
  { key: 'safe', label: 'بی‌خطر', variant: 'positive' },
  { key: 'normal', label: 'عادی', variant: 'info' },
  { key: 'near_limit', label: 'نزدیک سقف', variant: 'caution' },
  { key: 'over', label: 'بیش از بودجه', variant: 'critical' },
]

/**
 * The budget "کارنامه" — how the month actually went, category by category.
 *
 * The framing is deliberately neutral. Nothing here says "you did badly";
 * it reports the ratio of consumption to elapsed time and lets the user draw
 * their own conclusion, which is what the product principle asks for.
 */
export function BudgetPerformancePage() {
  const today = currentJalaliMonth()
  const [cursor, setCursor] = useState(today)
  const [bucket, setBucket] = useState<Bucket>('all')

  const { data, isPending, isError, error, refetch, isFetching } = useBudgetPerformance(
    cursor.year,
    cursor.month,
  )

  const analysis = data?.analysis
  // `total_categories` is the name the API uses; the fallback mirrors it so an
  // empty month shows `۰` rather than `undefined`.
  const summary = data?.summary ?? {
    safe: 0,
    normal: 0,
    near_limit: 0,
    over: 0,
    total_categories: 0,
  }

  const visible = useMemo(() => {
    const categories = analysis?.categories ?? []
    if (bucket === 'all') return categories

    return categories.filter((item) => item.status === bucket)
  }, [analysis?.categories, bucket])

  if (isError) {
    return (
      <ErrorState
        message={errorMessage(error, 'کارنامه بودجه دریافت نشد. دوباره تلاش کنید.')}
        onRetry={() => void refetch()}
        isRetrying={isFetching}
      />
    )
  }

  const headline = analysis
    ? describeMonth(Number(analysis.totals.consumed_percent), Number(analysis.time.elapsed_percent))
    : null

  return (
    <>
      <div className="mb-4 flex items-center gap-2">
        <Link
          to="/budgets"
          className="flex size-9 items-center justify-center rounded-control text-ink-soft transition-colors hover:bg-surface-muted"
          aria-label="بازگشت به بودجه‌ها"
        >
          <ArrowRight className="size-4" aria-hidden="true" />
        </Link>
        <div>
          <h1 className="text-lg font-bold text-ink lg:text-xl">کارنامه بودجه</h1>
          <p className="mt-0.5 text-[12.5px] text-ink-soft">
            مقایسه مصرف هر دسته با روند ماه
          </p>
        </div>
      </div>

      {/* Performance is a plan-versus-actual view, so a future month is
          meaningful: it shows the plan with nothing spent against it yet. */}
      <MonthNavigator
        year={cursor.year}
        month={cursor.month}
        onChange={(year, month) => setCursor({ year, month })}
        allowFuture
        className="mb-4"
      />

      {isPending ? (
        <div className="space-y-4">
          <LoadingCard />
          <LoadingCard />
        </div>
      ) : !analysis?.has_budget || analysis.categories.length === 0 ? (
        <Card padded={false}>
          <EmptyState
            title="داده‌ای برای این ماه وجود ندارد"
            description="برای مشاهده کارنامه، ابتدا بودجه این ماه را تعیین کنید."
            action={
              <Link
                to="/budgets"
                className="text-sm font-medium text-brand-600 hover:text-brand-700"
              >
                تعیین بودجه ماه
              </Link>
            }
          />
        </Card>
      ) : (
        <div className="space-y-4">
          {/* Headline verdict, stated as a comparison rather than a judgement */}
          <Card>
            <div className="flex items-start gap-3">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-control bg-brand-50 text-brand-600">
                <Info className="size-5" aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <p className="text-[14px] font-semibold text-ink">{headline?.title}</p>
                <p className="mt-1 text-[12.5px] leading-6 text-ink-soft">{headline?.body}</p>
              </div>
            </div>

            <div className="mt-4 grid grid-cols-2 gap-3 border-t border-border pt-4 sm:grid-cols-4">
              <Metric label="مصرف‌شده" value={analysis.totals.consumed_display} />
              <Metric label="گذشت ماه" value={analysis.time.elapsed_display} />
              <Metric label="کل بودجه" value={analysis.totals.budgeted_display} />
              <Metric
                label="باقی‌مانده"
                value={analysis.totals.remaining_display}
                tone={Number(analysis.totals.remaining) < 0 ? 'critical' : 'positive'}
              />
            </div>
          </Card>

          {/* Distribution */}
          <Card>
            <CardHeader
              title="وضعیت دسته‌بندی‌ها"
              subtitle={`${formatDigits(summary.total_categories)} دسته دارای بودجه`}
            />

            <div className="mt-4 space-y-3">
              <DistributionBar
                segments={[
                  { count: summary.safe, tone: 'positive', label: 'بی‌خطر' },
                  { count: summary.normal, tone: 'info', label: 'عادی' },
                  { count: summary.near_limit, tone: 'caution', label: 'نزدیک سقف' },
                  { count: summary.over, tone: 'critical', label: 'بیش از بودجه' },
                ]}
              />

              <div className="flex flex-wrap gap-2">
                {BUCKETS.map((option) => {
                  const count =
                    option.key === 'all'
                      ? summary.total_categories
                      : summary[option.key as BudgetStatus] ?? 0
                  const active = bucket === option.key

                  return (
                    <button
                      key={option.key}
                      type="button"
                      onClick={() => setBucket(option.key)}
                      aria-pressed={active}
                      className={[
                        'flex items-center gap-1.5 rounded-pill border px-3 py-1.5 text-[12px] transition-colors',
                        active
                          ? 'border-brand-500 bg-brand-50 font-medium text-brand-700'
                          : 'border-border bg-surface text-ink-soft hover:border-border-strong',
                      ].join(' ')}
                    >
                      {option.label}
                      <span className="ltr-nums text-[11px] text-ink-faint">
                        {formatDigits(count)}
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>
          </Card>

          {/* Per-category detail */}
          <section aria-label="جزئیات دسته‌بندی‌ها" className="space-y-2.5">
            {visible.length === 0 ? (
              <Card>
                <p className="py-6 text-center text-[13px] text-ink-faint">
                  در این وضعیت دسته‌ای وجود ندارد.
                </p>
              </Card>
            ) : (
              visible.map((item) => (
                <BudgetProgress
                  key={item.category_id}
                  analysis={item}
                  elapsedPercent={analysis.time.elapsed_percent}
                />
              ))
            )}
          </section>
        </div>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------

/**
 * Turns the consumption/elapsed pair into one sentence.
 *
 * Uses the same 15-point tolerance the server applies, and keeps the wording
 * descriptive — "سرعت مصرف بیشتر است" rather than "بیش از حد خرج کرده‌اید".
 */
function describeMonth(consumed: number, elapsed: number): { title: string; body: string } {
  const delta = consumed - elapsed

  if (consumed > 100) {
    return {
      title: 'جمع هزینه‌های این ماه از بودجه تعیین‌شده بیشتر شده است.',
      body: 'می‌توانید برای ماه بعد مبالغ را بازبینی کنید، یا دسته‌هایی که مصرف بیشتری داشته‌اند را جداگانه بررسی کنید.',
    }
  }

  if (delta > 15) {
    return {
      title: 'سرعت مصرف این ماه بیشتر از روند ماهانه است.',
      body: 'با این روند، بودجه پیش از پایان ماه مصرف می‌شود. بررسی دسته‌هایی که بیشترین مصرف را داشته‌اند می‌تواند کمک‌کننده باشد.',
    }
  }

  if (delta < -15) {
    return {
      title: 'مصرف شما از سرعت گذر ماه کمتر است.',
      body: 'تا اینجای ماه، هزینه‌ها پایین‌تر از بودجه تعیین‌شده پیش رفته است.',
    }
  }

  return {
    title: 'مصرف بودجه هم‌راستا با روند ماه پیش می‌رود.',
    body: 'هزینه‌ها متناسب با زمانی که از ماه گذشته، پیش رفته است.',
  }
}

function Metric({
  label,
  value,
  tone = 'neutral',
}: {
  label: string
  value: string
  tone?: 'neutral' | 'positive' | 'critical'
}) {
  const colour =
    tone === 'positive' ? 'text-positive-600' : tone === 'critical' ? 'text-critical-600' : 'text-ink'

  return (
    <div>
      <p className="text-[11.5px] text-ink-faint">{label}</p>
      <p className={['mt-1 text-[13.5px] font-semibold ltr-nums', colour].join(' ')}>{value}</p>
    </div>
  )
}

const SEGMENT_COLOURS = {
  positive: 'bg-positive-500',
  info: 'bg-info-500',
  caution: 'bg-caution-500',
  critical: 'bg-critical-500',
} as const

function DistributionBar({
  segments,
}: {
  segments: Array<{ count: number; tone: keyof typeof SEGMENT_COLOURS; label: string }>
}) {
  const total = segments.reduce((sum, segment) => sum + segment.count, 0)
  if (total === 0) return null

  return (
    <div
      className="flex h-2.5 w-full overflow-hidden rounded-pill bg-surface-muted"
      role="img"
      aria-label={segments
        .map((segment) => `${segment.label}: ${formatDigits(segment.count)} دسته`)
        .join('، ')}
    >
      {segments
        .filter((segment) => segment.count > 0)
        .map((segment) => (
          <span
            key={segment.label}
            className={SEGMENT_COLOURS[segment.tone]}
            style={{ width: `${(segment.count / total) * 100}%` }}
          />
        ))}
    </div>
  )
}
