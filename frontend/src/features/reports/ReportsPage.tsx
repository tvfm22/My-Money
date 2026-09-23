import { useMemo, useState } from 'react'
import { BarChart3 } from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Card, CardHeader } from '../../components/ui/Card'
import { Badge } from '../../components/ui/Badge'
import { EmptyState } from '../../components/ui/EmptyState'
import { ErrorState } from '../../components/ui/ErrorState'
import { LoadingCard } from '../../components/ui/LoadingState'
import { ProgressBar } from '../../components/ui/ProgressBar'
import { CategoryIcon } from '../../components/common/CategoryIcon'
import { SpendingTypeSplit } from '../../components/common/SpendingTypeSplit'
import { MonthNavigator } from '../../components/layout/MonthNavigator'
import { useReports } from '../../hooks/queries'
import { useChartPalette } from '../../utils/chartPalette'
import { errorMessage } from '../../services/client'
import { formatMoneyCompact, formatPercent, formatDigits } from '../../utils/format'
import { currentJalaliMonth } from '../../utils/jalali'
import type { BudgetStatus } from '../../types'

const STATUS_VARIANT: Record<BudgetStatus, 'positive' | 'info' | 'caution' | 'critical'> = {
  safe: 'positive',
  normal: 'info',
  near_limit: 'caution',
  over: 'critical',
}

/**
 * Reports.
 *
 * Four charts, each answering one question, in the order a person actually
 * asks them: where did the money go, how has spending moved over time, how
 * does income compare to expenses, and am I staying inside my budgets?
 * Deliberately not more than that — the spec warns against chart overload.
 */
export function ReportsPage() {
  const today = currentJalaliMonth()
  const [cursor, setCursor] = useState(today)
  const [activeSlice, setActiveSlice] = useState<number | null>(null)
  const palette = useChartPalette()

  const { data, isPending, isError, error, refetch, isFetching } = useReports({
    year: cursor.year,
    month: cursor.month,
    months: 6,
  })

  const donutData = useMemo(
    () =>
      (data?.spending_by_category.slices ?? []).map((slice) => ({
        name: slice.category_name,
        value: Number(slice.amount),
        display: slice.amount_display,
        share: slice.share_display,
        percent: Number(slice.share_percent),
        color: slice.color,
        icon: slice.icon,
        count: slice.count,
      })),
    [data?.spending_by_category.slices],
  )

  const trendData = useMemo(
    () =>
      (data?.monthly_trend ?? []).map((point) => ({
        label: point.label_short,
        income: Number(point.income),
        expense: Number(point.expense),
        net: Number(point.net),
      })),
    [data?.monthly_trend],
  )

  if (isError) {
    return (
      <ErrorState
        message={errorMessage(error, 'گزارش‌ها دریافت نشد. دوباره تلاش کنید.')}
        onRetry={() => void refetch()}
        isRetrying={isFetching}
      />
    )
  }

  const hasSpending = donutData.length > 0

  return (
    <>
      <div className="mb-4">
        <h1 className="text-lg font-bold text-ink lg:text-xl">گزارش‌ها</h1>
        <p className="mt-1 text-[12.5px] text-ink-soft">
          تصویری از الگوی درآمد و هزینه شما
        </p>
      </div>

      <MonthNavigator
        year={cursor.year}
        month={cursor.month}
        onChange={(year, month) => {
          setCursor({ year, month })
          setActiveSlice(null)
        }}
        className="mb-4"
      />

      {isPending ? (
        <div className="space-y-4">
          <LoadingCard />
          <LoadingCard />
        </div>
      ) : (
        <div className="space-y-4">
          {/* ------------------------------------------------------------ */}
          {/* Spending by category                                          */}
          {/* ------------------------------------------------------------ */}
          <Card>
            <CardHeader
              title="هزینه به تفکیک دسته‌بندی"
              subtitle={data?.month.label}
              action={
                data ? (
                  <span className="text-[12px] text-ink-soft">
                    جمع{' '}
                    <span className="ltr-nums font-semibold text-ink">
                      {data.spending_by_category.total_display}
                    </span>
                  </span>
                ) : null
              }
            />

            {!hasSpending ? (
              <EmptyState
                icon={<BarChart3 className="size-6" aria-hidden="true" />}
                title="در این ماه هزینه‌ای ثبت نشده است"
                description="با ثبت هزینه‌ها، نمودار تفکیک دسته‌بندی‌ها اینجا نمایش داده می‌شود."
              />
            ) : (
              <div className="mt-4 flex flex-col gap-5 sm:flex-row sm:items-center">
                {/* Donut */}
              <div className="relative mt-4 h-52 w-full shrink-0 sm:w-52" dir="ltr">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                      <Pie
                        data={donutData}
                        dataKey="value"
                        nameKey="name"
                        innerRadius="58%"
                        outerRadius="88%"
                        paddingAngle={2}
                        stroke={palette.stroke}
                        strokeWidth={2}
                        onMouseEnter={(_, index) => setActiveSlice(index)}
                        onMouseLeave={() => setActiveSlice(null)}
                      >
                        {donutData.map((slice, index) => (
                          <Cell
                            key={slice.name}
                            fill={slice.color}
                            opacity={activeSlice === null || activeSlice === index ? 1 : 0.35}
                          />
                        ))}
                      </Pie>
                      <Tooltip content={<SpendTooltip />} />
                    </PieChart>
                  </ResponsiveContainer>

                  {/* The donut hole carries the month's total — the single
                      number the chart exists to frame. */}
                  <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center" dir="rtl">
                    <p className="text-[10.5px] text-ink-faint">جمع هزینه</p>
                    <p className="ltr-nums mt-0.5 text-[15px] font-bold text-ink">
                      {formatMoneyCompact(Number(data?.spending_by_category.total))}
                    </p>
                  </div>
                </div>

                {/* Legend — the list is the real information carrier; the
                    donut is only a shape. */}
                <ul className="min-w-0 flex-1 space-y-2">
                  {donutData.slice(0, 7).map((slice, index) => (
                    <li
                      key={slice.name}
                      onMouseEnter={() => setActiveSlice(index)}
                      onMouseLeave={() => setActiveSlice(null)}
                      className={[
                        'flex items-center gap-2.5 rounded-control px-2 py-1.5 transition-colors',
                        activeSlice === index ? 'bg-surface-muted' : '',
                      ].join(' ')}
                    >
                      <span
                        className="size-2.5 shrink-0 rounded-pill"
                        style={{ backgroundColor: slice.color }}
                        aria-hidden="true"
                      />
                      <CategoryIcon
                        name={slice.icon}
                        color={slice.color}
                        size="sm"
                        filled={false}
                      />
                      <span className="min-w-0 flex-1 truncate text-[12.5px] text-ink">
                        {slice.name}
                      </span>
                      <span className="ltr-nums shrink-0 text-[12px] text-ink-soft">
                        {slice.display}
                      </span>
                      <span className="ltr-nums w-12 shrink-0 text-end text-[11px] text-ink-faint">
                        {slice.share}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Card>

          {/* ------------------------------------------------------------ */}
          {/* Spending by type (essential / flexible / wasted)              */}
          {/* ------------------------------------------------------------ */}
          {/* Optional-chained: a response cached before this field existed
              must not crash the whole page. */}
          {data && Number(data.spending_by_type?.total ?? 0) > 0 ? (
            <Card>
              <CardHeader
                title="نوع هزینه‌ها"
                subtitle="سهم هزینه‌های ضروری، انعطاف‌پذیر و غیرضروری"
                action={
                  <span className="text-[12px] text-ink-soft">
                    جمع{' '}
                    <span className="ltr-nums font-semibold text-ink">
                      {data.spending_by_type.total_display}
                    </span>
                  </span>
                }
              />
              <SpendingTypeSplit spendingTypes={data.spending_by_type} className="mt-4" />
            </Card>
          ) : null}
          {/* ------------------------------------------------------------ */}
          {/* Monthly trend                                                 */}
          {/* ------------------------------------------------------------ */}
          {trendData.length > 1 ? (
            <Card>
              <CardHeader title="روند ماهانه" subtitle="درآمد و هزینه شش ماه اخیر" />

              <div className="mt-4 h-56 w-full" dir="ltr">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={trendData} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={palette.grid} vertical={false} />
                    <XAxis
                      dataKey="label"
                      tick={{ fontSize: 10, fill: palette.tick }}
                      axisLine={false}
                      tickLine={false}
                      reversed
                    />
                    <YAxis
                      tick={{ fontSize: 10, fill: palette.tick }}
                      axisLine={false}
                      tickLine={false}
                      orientation="right"
                      width={54}
                      tickFormatter={(value: number) => formatMoneyCompact(value, { latin: true })}
                    />
                    <Tooltip content={<TrendTooltip />} cursor={{ fill: 'rgba(0,0,0,0.03)' }} />
                    <Legend
                      wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
                      formatter={(value: string) => (
                        <span style={{ color: palette.tick }}>{value}</span>
                      )}
                    />
                    <Bar
                      dataKey="income"
                      name="درآمد"
                      fill={palette.income}
                      radius={[4, 4, 0, 0]}
                      maxBarSize={22}
                    />
                    <Bar
                      dataKey="expense"
                      name="هزینه"
                      fill={palette.expense}
                      radius={[4, 4, 0, 0]}
                      maxBarSize={22}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
          ) : null}

          {/* ------------------------------------------------------------ */}
          {/* Budget vs actual                                              */}
          {/* ------------------------------------------------------------ */}
          {data && data.budget_vs_actual.length > 0 ? (
            <Card padded={false}>
              <div className="border-b border-border px-4 py-3.5 sm:px-5">
                <h2 className="text-[15px] font-semibold text-ink">بودجه در برابر واقعیت</h2>
                <p className="mt-0.5 text-xs text-ink-faint">
                  مقایسه مبلغ تعیین‌شده با هزینه واقعی هر دسته
                </p>
              </div>

              <ul className="divide-y divide-border">
                {data.budget_vs_actual.map((row) => {
                  const budgeted = Number(row.budgeted)
                  const actual = Number(row.actual)
                  const percent = budgeted > 0 ? (actual / budgeted) * 100 : 0
                  // Only slices that actually carry money — a category with no
                  // wasted spend should not grow a "غیرضروری ۰٪" line.
                  const typeSplit =
                    row.spending_types?.buckets.filter((b) => Number(b.amount) > 0) ?? []

                  return (
                    <li key={row.category_id} className="px-4 py-3.5 sm:px-5">
                      <div className="flex items-center gap-3">
                        <CategoryIcon name={row.icon} color={row.color} size="sm" />

                        <div className="min-w-0 flex-1">
                          <div className="flex items-center justify-between gap-2">
                            <span className="truncate text-[13px] font-medium text-ink">
                              {row.category_name}
                            </span>
                            <Badge variant={STATUS_VARIANT[row.status]} size="sm">
                              <span className="ltr-nums">{formatPercent(percent)}</span>
                            </Badge>
                          </div>

                          <p className="mt-1 text-[11.5px] text-ink-faint">
                            <span className="ltr-nums">{row.actual_display}</span>
                            {' از '}
                            <span className="ltr-nums">{row.budgeted_display}</span>
                          </p>

                          <ProgressBar
                            value={percent}
                            tone={
                              row.status === 'over'
                                ? 'critical'
                                : row.status === 'near_limit'
                                  ? 'caution'
                                  : row.status === 'safe'
                                    ? 'positive'
                                    : 'info'
                            }
                            size="sm"
                            label={`${row.category_name}: ${row.budgeted_display}`}
                            className="mt-2"
                          />

                          {typeSplit.length > 0 ? (
                            <p className="mt-2 text-[11px] text-ink-faint">
                              {typeSplit.map((bucket, index) => (
                                <span key={bucket.key}>
                                  {index > 0 ? <span aria-hidden="true"> · </span> : null}
                                  {bucket.label}{' '}
                                  <span className="ltr-nums">{bucket.share_display}</span>
                                </span>
                              ))}
                            </p>
                          ) : null}
                        </div>

                        <div className="shrink-0 text-end">
                          <p
                            className={[
                              'ltr-nums text-[12px] font-medium',
                              Number(row.difference) >= 0 ? 'text-positive-600' : 'text-critical-600',
                            ].join(' ')}
                          >
                            {row.difference_display}
                          </p>
                          <p className="mt-0.5 text-[10px] text-ink-faint">
                            {Number(row.difference) >= 0 ? 'باقی‌مانده' : 'بیش از بودجه'}
                          </p>
                        </div>
                      </div>
                    </li>
                  )
                })}
              </ul>
            </Card>
          ) : null}

          {/* ------------------------------------------------------------ */}
          {/* Net worth history                                             */}
          {/* ------------------------------------------------------------ */}
          {data && data.net_worth_history.length > 1 ? (
            <Card>
              <CardHeader title="روند ثروت خالص" subtitle="در ماه‌های گذشته" />

              <div className="mt-4 h-52 w-full" dir="ltr">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={data.net_worth_history.map((point) => ({
                      label: point.month_name,
                      netWorth: Number(point.net_worth),
                    }))}
                    margin={{ top: 4, right: 4, bottom: 0, left: 4 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke={palette.grid} vertical={false} />
                    <XAxis
                      dataKey="label"
                      tick={{ fontSize: 10, fill: palette.tick }}
                      axisLine={false}
                      tickLine={false}
                      reversed
                    />
                    <YAxis
                      tick={{ fontSize: 10, fill: palette.tick }}
                      axisLine={false}
                      tickLine={false}
                      orientation="right"
                      width={54}
                      tickFormatter={(value: number) => formatMoneyCompact(value, { latin: true })}
                    />
                    <Tooltip content={<NetWorthTooltip />} />
                    <Line
                      type="monotone"
                      dataKey="netWorth"
                      stroke={palette.brand}
                      strokeWidth={2}
                      dot={{ r: 2.5, fill: palette.brand }}
                      activeDot={{ r: 4 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Card>
          ) : null}

          {/* ------------------------------------------------------------ */}
          {/* Asset breakdown                                               */}
          {/* ------------------------------------------------------------ */}
          {data && data.asset_breakdown.length > 0 ? (
            <Card>
              <CardHeader title="ترکیب دارایی‌ها" subtitle="سهم هر نوع از کل ارزش" />
              <ul className="mt-4 space-y-3">
                {data.asset_breakdown.map((row) => (
                  <li key={row.type}>
                    <div className="mb-1.5 flex items-baseline justify-between gap-2">
                      <span className="text-[12.5px] text-ink-soft">{row.label}</span>
                      <span className="flex items-center gap-2">
                        <span className="ltr-nums text-[12px] font-medium text-ink">
                          {row.total_display}
                        </span>
                        <span className="ltr-nums text-[11px] text-ink-faint">
                          {formatPercent(Number(row.share_percent))}
                        </span>
                      </span>
                    </div>
                    <ProgressBar
                      value={Number(row.share_percent)}
                      tone="brand"
                      size="sm"
                      label={`سهم ${row.label}`}
                    />
                  </li>
                ))}
              </ul>
            </Card>
          ) : null}
        </div>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// Chart tooltips — kept RTL and in Persian, unlike the Recharts default.
// ---------------------------------------------------------------------------

function SpendTooltip({
  active,
  payload,
}: {
  active?: boolean
  payload?: Array<{ payload: { name: string; display: string; share: string; count: number } }>
}) {
  if (!active || !payload?.length) return null
  const slice = payload[0].payload

  return (
    <div className="rounded-control border border-border bg-surface px-3 py-2 shadow-raised" dir="rtl">
      <p className="text-[11.5px] font-medium text-ink">{slice.name}</p>
      <p className="mt-1 text-[11.5px] text-ink-soft">
        <span className="ltr-nums font-semibold text-ink">{slice.display}</span>
        {' • '}
        <span className="ltr-nums">{slice.share}</span>
      </p>
      <p className="text-[10.5px] text-ink-faint">
        <span className="ltr-nums">{formatDigits(slice.count)}</span> تراکنش
      </p>
    </div>
  )
}

function TrendTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: Array<{ name: string; value: number; color: string }>
  label?: string
}) {
  if (!active || !payload?.length) return null

  return (
    <div className="rounded-control border border-border bg-surface px-3 py-2 shadow-raised" dir="rtl">
      <p className="text-[11.5px] font-medium text-ink">{label}</p>
      {payload.map((entry) => (
        <p key={entry.name} className="mt-0.5 text-[11px] text-ink-soft">
          {entry.name}{' '}
          <span className="ltr-nums font-semibold" style={{ color: entry.color }}>
            {formatMoneyCompact(entry.value)}
          </span>
        </p>
      ))}
    </div>
  )
}

function NetWorthTooltip({
  active,
  payload,
}: {
  active?: boolean
  payload?: Array<{ payload: { label: string; netWorth: number } }>
}) {
  if (!active || !payload?.length) return null

  return (
    <div className="rounded-control border border-border bg-surface px-3 py-2 shadow-raised" dir="rtl">
      <p className="text-[11.5px] font-medium text-ink">{payload[0].payload.label}</p>
      <p className="mt-1 text-[11px] text-ink-soft">
        {'ثروت خالص: '}
        <span className="ltr-nums font-semibold text-ink">
          {formatMoneyCompact(payload[0].payload.netWorth)}
        </span>
      </p>
    </div>
  )
}
