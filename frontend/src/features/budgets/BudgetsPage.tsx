import { useEffect, useId, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Copy, PieChart, Plus, Save } from 'lucide-react'
import { Card, CardHeader } from '../../components/ui/Card'
import { Button } from '../../components/ui/Button'
import { Badge } from '../../components/ui/Badge'
import { useToast } from '../../components/ui/Toast'
import { ProgressBar } from '../../components/ui/ProgressBar'
import { EmptyState } from '../../components/ui/EmptyState'
import { ErrorState } from '../../components/ui/ErrorState'
import { LoadingCard } from '../../components/ui/LoadingState'
import { CategoryIcon } from '../../components/common/CategoryIcon'
import { BudgetProgress } from '../../components/common/BudgetProgress'
import { CategoryDrillDown } from './CategoryDrillDown'
import { MoneyDisplay } from '../../components/common/MoneyDisplay'
import { MonthNavigator } from '../../components/layout/MonthNavigator'
import {
  useBudgetAnalysis,
  useCategoryPicker,
  useCopyBudget,
  useSaveBudgetPlan,
} from '../../hooks/queries'
import { errorMessage } from '../../services/client'
import { ZERO_PLACEHOLDER, formatDigits, formatMoney, normalizeNumericInput, toLatinDigits } from '../../utils/format'
import { currentJalaliMonth, jalaliMonthBounds } from '../../utils/jalali'
import type { BudgetStatus } from '../../types'

type Draft = Record<string | number, string>

/** The category currently opened in the drill-down, kept mounted once chosen. */
interface DrillTarget {
  id: number
  name: string
  icon: string
  color: string
}

/**
 * The budget plan screen.
 *
 * Three things live here, in order of importance:
 *  1. the month's plan (expected income, savings, debt payments, free budget),
 *  2. per-category allocation with live consumption feedback,
 *  3. a status summary so the user can see the month's shape at a glance.
 */
export function BudgetsPage() {
  const today = currentJalaliMonth()
  const [cursor, setCursor] = useState(today)
  const [isEditing, setIsEditing] = useState(false)
  const [draft, setDraft] = useState<Draft>({})
  const [planError, setPlanError] = useState<string | null>(null)
  const [drillTarget, setDrillTarget] = useState<DrillTarget | null>(null)
  const [isDrillOpen, setIsDrillOpen] = useState(false)

  const { data: analysis, isPending, isError, error, refetch, isFetching } = useBudgetAnalysis(
    cursor.year,
    cursor.month,
  )
  const { data: categories } = useCategoryPicker('expense')
  const savePlan = useSaveBudgetPlan()
  const copyBudget = useCopyBudget()
  const { showToast } = useToast()

  // Only categories that already have an allocation, or all of them while
  // editing — an empty plan should not render 21 identical zero rows.
  const rows = useMemo(() => {
    const list = categories ?? []
    if (isEditing) return list
    const budgetedIds = new Set((analysis?.categories ?? []).map((c) => c.category_id))
    return list.filter((c) => budgetedIds.has(c.id))
  }, [categories, analysis?.categories, isEditing])

  /**
   * The sum of the category allocations — and only those.
   *
   * This used to sum `Object.values(draft)`, but `draft` holds the plan-level
   * fields (`expectedIncome`, `savingsTarget`, `investmentTarget`, `debtTarget`)
   * alongside the per-category amounts, keyed by string rather than by category
   * id. So the income envelope was counted as if it were an allocation, and then
   * subtracted again below — the total came out at roughly double the income and
   * the form declared itself oversubscribed no matter what was typed. The effect
   * was that the plan could never be saved at all.
   *
   * Summing over `rows` is both correct and self-documenting: the allocations
   * are exactly the rows on screen.
   */
  const allocatedTotal = useMemo(
    () =>
      rows.reduce(
        (sum, category) =>
          sum + (Number(normalizeNumericInput(draft[category.id] ?? '')) || 0),
        0,
      ),
    [draft, rows],
  )

  const expectedIncome = Number(normalizeNumericInput(draft.expectedIncome ?? '')) || 0
  const savingsTarget = Number(normalizeNumericInput(draft.savingsTarget ?? '')) || 0
  const investmentTarget = Number(normalizeNumericInput(draft.investmentTarget ?? '')) || 0
  const debtTarget = Number(normalizeNumericInput(draft.debtTarget ?? '')) || 0

  const free = expectedIncome - allocatedTotal - savingsTarget - investmentTarget - debtTarget
  const oversubscribed = free < 0

  // Seed the draft from the server's plan whenever we enter edit mode.
  useEffect(() => {
    if (!isEditing || !analysis) return
    const next: Draft = {
      expectedIncome: String(Math.round(Number(analysis.plan.expected_income || 0))) || '',
      savingsTarget: String(Math.round(Number(analysis.plan.savings_target || 0))) || '',
      investmentTarget: String(Math.round(Number(analysis.plan.investment_target || 0))) || '',
      debtTarget: String(Math.round(Number(analysis.plan.debt_payment_target || 0))) || '',
    }
    for (const item of analysis.categories) {
      next[item.category_id] = String(Math.round(Number(item.budgeted || 0))) || ''
    }
    setDraft(next)
  }, [isEditing, analysis])

  const setAmount = (key: number | string, raw: string) => {
    setPlanError(null)
    const latin = toLatinDigits(raw).replace(/[^\d]/g, '')
    setDraft((current) => ({ ...current, [key]: latin }))
  }

  const submitPlan = () => {
    // The server's field is `allocations`. Sending `items` was accepted with a
    // 200 and then ignored, because DRF drops keys the serializer does not
    // declare — so saving appeared to work and changed nothing.
    const allocations = rows
      .map((category) => ({
        category: category.id,
        amount: String(Number(normalizeNumericInput(draft[category.id] ?? '')) || 0),
      }))
      .filter((item) => Number(item.amount) > 0)

    if (allocations.length === 0) {
      setPlanError('برای تعیین بودجه، مبلغ حداقل یک دسته‌بندی را وارد کنید.')
      return
    }
    if (oversubscribed) {
      setPlanError('جمع بودجه‌ها از درآمد پیش‌بینی‌شده بیشتر است. مبالغ را بازبینی کنید.')
      return
    }

    savePlan.mutate(
      {
        year: cursor.year,
        month: cursor.month,
        expected_income: String(expectedIncome),
        savings_target: String(savingsTarget),
        investment_target: String(investmentTarget),
        debt_payment_target: String(debtTarget),
        allocations,
      },
      {
        onSuccess: () => {
          setIsEditing(false)
          setPlanError(null)
          showToast({ message: 'برنامه بودجه ذخیره شد.' })
        },
        onError: (err) =>
          setPlanError(errorMessage(err, 'ذخیره بودجه انجام نشد. دوباره تلاش کنید.')),
      },
    )
  }

  const startEditing = () => {
    setPlanError(null)
    setIsEditing(true)
  }

  const cancelEditing = () => {
    setIsEditing(false)
    setDraft({})
    setPlanError(null)
  }

  const previousMonth = useMemo(() => {
    const bounds = jalaliMonthBounds(cursor.year, cursor.month)
    void bounds
    return cursor.month === 1
      ? { year: cursor.year - 1, month: 12 }
      : { year: cursor.year, month: cursor.month - 1 }
  }, [cursor])

  const statusCounts = useMemo(() => {
    const counts: Record<BudgetStatus, number> = {
      safe: 0,
      normal: 0,
      near_limit: 0,
      over: 0,
    }
    for (const item of analysis?.categories ?? []) counts[item.status] += 1
    return counts
  }, [analysis?.categories])

  if (isError) {
    return (
      <ErrorState
        message={errorMessage(error, 'اطلاعات بودجه دریافت نشد. دوباره تلاش کنید.')}
        onRetry={() => void refetch()}
        isRetrying={isFetching}
      />
    )
  }

  return (
    <>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-bold text-ink lg:text-xl">بودجه‌ها</h1>
          <p className="mt-1 text-[12.5px] text-ink-soft">
            برنامه مالی ماه و میزان مصرف هر دسته
          </p>
        </div>

        <Link to="/budgets/performance">
          <Button variant="secondary" size="sm">
            کارنامه بودجه
          </Button>
        </Link>
      </div>

      {/* Budgets are a plan, so the user has to reach next month to set one.
          Forward travel is capped at a year by the component itself. */}
      <MonthNavigator
        year={cursor.year}
        month={cursor.month}
        onChange={(year, month) => {
          setCursor({ year, month })
          setIsEditing(false)
          setIsDrillOpen(false)
        }}
        allowFuture
        className="mb-4"
      />

      {isPending ? (
        <div className="space-y-4">
          <LoadingCard />
          <LoadingCard />
        </div>
      ) : isEditing ? (
        /* ------------------------------------------------------------ */
        /* Plan editor                                                   */
        /* ------------------------------------------------------------ */
        <div className="space-y-4">
          <Card>
            <CardHeader
              title="برنامه مالی ماه"
              subtitle="درآمد پیش‌بینی‌شده و اهداف خود را مشخص کنید"
            />

            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <MoneyField
                label="درآمد پیش‌بینی‌شده"
                value={draft.expectedIncome ?? ''}
                onChange={(value) => setAmount('expectedIncome', value)}
              />
              <MoneyField
                label="پس‌انداز هدف"
                value={draft.savingsTarget ?? ''}
                onChange={(value) => setAmount('savingsTarget', value)}
              />
              <MoneyField
                label="سرمایه‌گذاری هدف"
                value={draft.investmentTarget ?? ''}
                onChange={(value) => setAmount('investmentTarget', value)}
              />
              <MoneyField
                label="پرداخت بدهی"
                value={draft.debtTarget ?? ''}
                onChange={(value) => setAmount('debtTarget', value)}
              />
            </div>

            <div className="mt-4 space-y-1.5 rounded-card bg-surface-muted p-3">
              <SummaryLine label="جمع بودجه دسته‌ها" value={allocatedTotal} />
              <SummaryLine label="پس‌انداز و سرمایه‌گذاری" value={savingsTarget + investmentTarget} />
              <SummaryLine label="پرداخت بدهی" value={debtTarget} />
              <div className="border-t border-border pt-1.5">
                <SummaryLine
                  label={oversubscribed ? 'کسری بودجه' : 'بودجه آزاد'}
                  value={free}
                  tone={oversubscribed ? 'critical' : 'positive'}
                  bold
                />
              </div>
            </div>
          </Card>

          <Card padded={false}>
            <div className="border-b border-border px-4 py-3.5 sm:px-5">
              <h2 className="text-[15px] font-semibold text-ink">بودجه دسته‌بندی‌ها</h2>
              <p className="mt-0.5 text-xs text-ink-faint">
                برای هر دسته مبلغ ماهانه تعیین کنید. خالی گذاشتن یعنی بدون بودجه.
              </p>
            </div>

            <ul className="divide-y divide-border">
              {rows.map((category) => (
                <li key={category.id} className="flex items-center gap-3 px-4 py-2.5 sm:px-5">
                  <CategoryIcon name={category.icon} color={category.color} size="sm" />
                  <span className="min-w-0 flex-1 truncate text-[13px] text-ink">
                    {category.name}
                  </span>
                  <input
                    inputMode="numeric"
                    dir="ltr"
                    placeholder={ZERO_PLACEHOLDER}
                    value={
                      draft[category.id] ? formatDigits(Number(draft[category.id])) : ''
                    }
                    onChange={(event) => setAmount(category.id, event.target.value)}
                    aria-label={`بودجه ${category.name}`}
                    className="h-10 w-32 rounded-control border border-border-strong bg-surface px-3 text-end text-[13px] text-ink ltr-nums placeholder:text-ink-faint focus:border-brand-500"
                  />
                </li>
              ))}
            </ul>
          </Card>

          {planError ? (
            <p role="alert" className="rounded-control bg-critical-50 px-3 py-2 text-xs text-critical-700">
              {planError}
            </p>
          ) : null}

          <div className="flex gap-2">
            <Button
              onClick={submitPlan}
              isLoading={savePlan.isPending}
              className="flex-1"
              leadingIcon={<Save className="size-4" aria-hidden="true" />}
            >
              ذخیره برنامه ماه
            </Button>
            <Button variant="secondary" onClick={cancelEditing} className="flex-1">
              انصراف
            </Button>
          </div>
        </div>
      ) : (
        /* ------------------------------------------------------------ */
        /* Read-only month view                                          */
        /* ------------------------------------------------------------ */
        <div className="space-y-4">
          {!analysis?.has_budget ? (
            <Card padded={false}>
              <EmptyState
                icon={<PieChart className="size-6" aria-hidden="true" />}
                title="برای این ماه بودجه‌ای تعیین نشده"
                description="با تعیین بودجه، سرعت مصرف هر دسته را در طول ماه می‌بینید و می‌دانید چقدر جای مانور دارید."
                action={
                  <div className="flex flex-wrap justify-center gap-2">
                    <Button
                      size="sm"
                      onClick={startEditing}
                      leadingIcon={<Plus className="size-4" aria-hidden="true" />}
                    >
                      تعیین بودجه
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      isLoading={copyBudget.isPending}
                      onClick={() =>
                        copyBudget.mutate(
                          {
                            fromYear: previousMonth.year,
                            fromMonth: previousMonth.month,
                            toYear: cursor.year,
                            toMonth: cursor.month,
                          },
                          {
                            onSuccess: () =>
                              showToast({ message: 'بودجه ماه قبل کپی شد.' }),
                          },
                        )
                      }
                      leadingIcon={<Copy className="size-3.5" aria-hidden="true" />}
                    >
                      کپی از ماه قبل
                    </Button>
                  </div>
                }
              />
            </Card>
          ) : (
            <>
              {/* Plan summary */}
              <Card>
                <CardHeader
                  title="برنامه مالی ماه"
                  action={
                    <>
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={startEditing}
                        leadingIcon={<Plus className="size-3.5" aria-hidden="true" />}
                      >
                        ویرایش
                      </Button>
                    </>
                  }
                />

                <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <MiniStat label="درآمد پیش‌بینی‌شده" value={analysis.plan.expected_income} />
                  <MiniStat label="درآمد واقعی" value={analysis.actuals.income} tone="positive" />
                  <MiniStat label="هزینه واقعی" value={analysis.actuals.expense} tone="negative" />
                  <MiniStat
                    label={analysis.plan.is_oversubscribed ? 'کسری بودجه' : 'بودجه آزاد'}
                    value={analysis.plan.flexible_budget}
                    tone={analysis.plan.is_oversubscribed ? 'negative' : 'positive'}
                  />
                </dl>

                {analysis.plan.is_oversubscribed ? (
                  <p className="mt-3 rounded-control bg-caution-50 px-3 py-2 text-[11.5px] leading-5 text-caution-700">
                    جمع بودجه‌های تعیین‌شده از درآمد پیش‌بینی‌شده بیشتر است.
                  </p>
                ) : null}
              </Card>

              {/* Overall consumption */}
              <Card>
                <CardHeader
                  title="میزان مصرف کل"
                  subtitle={`${formatDigits(analysis.time.days_elapsed)} روز از ${formatDigits(analysis.time.days_in_month)} روز ماه گذشته`}
                />

                <div className="mt-4 space-y-2.5">
                  <div className="flex items-baseline justify-between">
                    <span className="text-[13px] text-ink-soft">
                      <span className="ltr-nums font-semibold text-ink">
                        {analysis.totals.spent_display}
                      </span>
                      {' از '}
                      <span className="ltr-nums">{analysis.totals.budgeted_display}</span>
                    </span>
                    <span className="ltr-nums text-[13px] font-semibold text-ink">
                      {analysis.totals.consumed_display}
                    </span>
                  </div>

                  <ProgressBar
                    value={Number(analysis.totals.consumed_percent || 0)}
                    tone={
                      Number(analysis.totals.consumed_percent) > 100
                        ? 'critical'
                        : Number(analysis.totals.consumed_percent) >= 80
                          ? 'caution'
                          : 'positive'
                    }
                    size="lg"
                    markerPercent={Number(analysis.time.elapsed_percent || 0)}
                    label="میزان مصرف کل بودجه"
                  />

                  <div className="flex items-center justify-between text-[11.5px] text-ink-faint">
                    <span>
                      {'گذشت ماه: '}
                      <span className="ltr-nums">{analysis.time.elapsed_display}</span>
                    </span>
                    <span>
                      {'باقی‌مانده بودجه: '}
                      <span className="ltr-nums text-ink-soft">
                        {analysis.totals.remaining_display}
                      </span>
                    </span>
                  </div>
                </div>

                {/* Status tally — the shape of the month in four numbers. */}
                <div className="mt-4 grid grid-cols-4 gap-2 border-t border-border pt-3.5">
                  <StatusTally label="بی‌خطر" count={statusCounts.safe} variant="positive" />
                  <StatusTally label="عادی" count={statusCounts.normal} variant="info" />
                  <StatusTally label="نزدیک سقف" count={statusCounts.near_limit} variant="caution" />
                  <StatusTally label="بیش از بودجه" count={statusCounts.over} variant="critical" />
                </div>
              </Card>

              {/* Per category */}
              <section aria-label="بودجه دسته‌بندی‌ها" className="space-y-2.5">
                <div className="flex items-center justify-between px-1">
                  <h2 className="text-[15px] font-semibold text-ink">دسته‌بندی‌ها</h2>
                  <Link
                    to="/budgets/performance"
                    className="text-xs font-medium text-brand-600 hover:text-brand-700"
                  >
                    کارنامه کامل
                  </Link>
                </div>

                {analysis.categories.length === 0 ? (
                  <Card>
                    <p className="py-6 text-center text-[13px] text-ink-faint">
                      هنوز برای هیچ دسته‌ای بودجه تعیین نشده است.
                    </p>
                  </Card>
                ) : (
                  analysis.categories.map((item) => (
                    <BudgetProgress
                      key={item.category_id}
                      analysis={item}
                      elapsedPercent={analysis.time.elapsed_percent}
                      // Tapping a budgeted category opens the month's
                      // itemised expenses for it.
                      onClick={() => {
                        setDrillTarget({
                          id: item.category_id,
                          name: item.category_name,
                          icon: item.category_icon,
                          color: item.category_color,
                        })
                        setIsDrillOpen(true)
                      }}
                    />
                  ))
                )}
              </section>
            </>
          )}
        </div>
      )}

      {drillTarget ? (
        <CategoryDrillDown
          open={isDrillOpen}
          onClose={() => setIsDrillOpen(false)}
          categoryId={drillTarget.id}
          name={drillTarget.name}
          icon={drillTarget.icon}
          color={drillTarget.color}
          year={cursor.year}
          month={cursor.month}
        />
      ) : null}
    </>
  )
}

// ---------------------------------------------------------------------------
// Small local pieces
// ---------------------------------------------------------------------------

function MoneyField({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (value: string) => void
}) {
  // A `<label>` with neither `htmlFor` nor a wrapped control is inert — it
  // cannot be clicked to focus the field and screen readers do not announce it
  // as that input's name.
  const inputId = `budget-amount-${useId()}`

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={inputId} className="text-[13px] font-medium text-ink-soft">
        {label}
      </label>
      <div className="relative">
        <input
          id={inputId}
          inputMode="numeric"
          dir="ltr"
          placeholder={ZERO_PLACEHOLDER}
          value={value ? formatDigits(Number(value)) : ''}
          onChange={(event) => onChange(event.target.value)}
          className="h-11 w-full rounded-control border border-border-strong bg-surface px-3 text-sm text-ink ltr-nums placeholder:text-ink-faint focus:border-brand-500"
        />
        <span className="pointer-events-none absolute inset-y-0 start-3 flex items-center text-[11px] text-ink-faint">
          تومان
        </span>
      </div>
    </div>
  )
}

function SummaryLine({
  label,
  value,
  tone = 'neutral',
  bold = false,
}: {
  label: string
  value: number
  tone?: 'neutral' | 'positive' | 'critical'
  bold?: boolean
}) {
  const colour =
    tone === 'critical' ? 'text-critical-600' : tone === 'positive' ? 'text-positive-600' : 'text-ink'

  return (
    <div className="flex items-center justify-between gap-2">
      <span className={['text-[12.5px]', bold ? 'font-semibold text-ink' : 'text-ink-soft'].join(' ')}>
        {label}
      </span>
      <span
        className={[
          'ltr-nums text-[12.5px]',
          colour,
          bold ? 'font-semibold' : 'font-medium',
        ].join(' ')}
      >
        {formatMoney(String(Math.abs(value)))}
        {value < 0 ? ' کسری' : ''}
      </span>
    </div>
  )
}

function MiniStat({
  label,
  value,
  tone = 'neutral',
}: {
  label: string
  value: string
  tone?: 'neutral' | 'positive' | 'negative'
}) {
  const colour =
    tone === 'positive' ? 'text-positive-600' : tone === 'negative' ? 'text-critical-600' : 'text-ink'

  return (
    <div>
      <dt className="text-[11.5px] text-ink-faint">{label}</dt>
      <dd className={['mt-1 text-[13px] font-semibold', colour].join(' ')}>
        <MoneyDisplay value={value} compact />
      </dd>
    </div>
  )
}

function StatusTally({
  label,
  count,
  variant,
}: {
  label: string
  count: number
  variant: 'positive' | 'info' | 'caution' | 'critical'
}) {
  return (
    <div className="text-center">
      <Badge variant={variant} size="sm" className="mx-auto">
        <span className="ltr-nums">{formatDigits(count)}</span>
      </Badge>
      <p className="mt-1.5 text-[10.5px] leading-4 text-ink-faint">{label}</p>
    </div>
  )
}
