import { AlertTriangle, CheckCircle2, Minus, TrendingUp } from 'lucide-react'
import type { BudgetCategoryAnalysis, BudgetStatus } from '../../types'
import { CategoryIcon } from './CategoryIcon'
import { ProgressBar } from '../ui/ProgressBar'
import type { ProgressTone } from '../ui/ProgressBar'
import { Badge } from '../ui/Badge'
import { formatPercent } from '../../utils/format'

/**
 * Maps a server-side budget status onto a progress tone.
 *
 * The server owns the *classification* (it knows the thresholds); this map
 * only decides how to paint it. Keeping it a pure mapping means the two can
 * never drift apart.
 */
export const STATUS_TONE: Record<BudgetStatus, ProgressTone> = {
  safe: 'positive',
  normal: 'info',
  near_limit: 'caution',
  over: 'critical',
}

const STATUS_BADGE_VARIANT = {
  safe: 'positive',
  normal: 'info',
  near_limit: 'caution',
  over: 'critical',
} as const

const STATUS_ICON = {
  safe: CheckCircle2,
  normal: Minus,
  near_limit: AlertTriangle,
  over: AlertTriangle,
} as const

export interface BudgetProgressProps {
  analysis: BudgetCategoryAnalysis
  /** How far through the month we are, as a percentage, for the pace marker. */
  elapsedPercent?: string | number
  onClick?: () => void
  className?: string
}

/**
 * A single budget's consumption, with the pace marker.
 *
 * This is the component that answers the spec's central question — "is my
 * spending appropriate relative to my budget?" — by putting two things next
 * to each other: how much of the budget is used (the fill) and how much of
 * the month has passed (the marker). The status badge carries the
 * classification; the server's longer commentary sentence is deliberately
 * not rendered — it repeated what the numbers already say.
 */
export function BudgetProgress({
  analysis,
  elapsedPercent,
  onClick,
  className = '',
}: BudgetProgressProps) {
  const consumed = Number(analysis.consumed_percent || 0)
  const elapsed =
    elapsedPercent === undefined ? undefined : Number(elapsedPercent || 0)

  const StatusGlyph = STATUS_ICON[analysis.status]
  const tone = STATUS_TONE[analysis.status]

  const Wrapper = onClick ? 'button' : 'div'

  return (
    <Wrapper
      {...(onClick ? { type: 'button' as const, onClick } : {})}
      className={[
        'w-full rounded-card border border-border bg-surface p-4 text-start',
        onClick ? 'transition-colors hover:bg-surface-muted/50' : '',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <div className="flex items-start gap-3">
        <CategoryIcon name={analysis.category_icon} color={analysis.category_color} size="md" />

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate text-[13.5px] font-semibold text-ink">
                {analysis.category_name}
              </p>
              <p className="mt-0.5 text-[11.5px] text-ink-faint">
                <span className="ltr-nums">{analysis.spent_display}</span>
                {' از '}
                <span className="ltr-nums">{analysis.budgeted_display}</span>
              </p>
            </div>

            <div className="flex shrink-0 flex-col items-end gap-1">
              <span
                className={[
                  'ltr-nums text-[13px] font-semibold',
                  analysis.status === 'over'
                    ? 'text-critical-600'
                    : analysis.status === 'near_limit'
                      ? 'text-caution-700'
                      : 'text-ink',
                ].join(' ')}
              >
                {formatPercent(consumed)}
              </span>
              <Badge variant={STATUS_BADGE_VARIANT[analysis.status]} size="sm" icon={<StatusGlyph className="size-3" aria-hidden="true" />}>
                {analysis.status_label}
              </Badge>
            </div>
          </div>

          <ProgressBar
            value={consumed}
            tone={tone}
            size="md"
            markerPercent={elapsed}
            label={`میزان مصرف بودجه ${analysis.category_name}`}
            className="mt-3"
          />

          <div className="mt-2 flex items-center justify-between gap-2 text-[11.5px] text-ink-faint">
            <span>
              {analysis.status === 'over' && analysis.over_budget_display ? (
                <span className="text-critical-600">
                  {'بیش از بودجه: '}
                  <span className="ltr-nums">{analysis.over_budget_display}</span>
                </span>
              ) : (
                <>
                  {'باقی‌مانده: '}
                  <span className="ltr-nums text-ink-soft">{analysis.remaining_display}</span>
                </>
              )}
            </span>

            {analysis.projected_display && analysis.status !== 'over' ? (
              <span className="flex items-center gap-1">
                <TrendingUp className="size-3" aria-hidden="true" />
                <span>
                  {'پیش‌بینی پایان ماه: '}
                  <span className="ltr-nums">{analysis.projected_display}</span>
                </span>
              </span>
            ) : null}
          </div>
        </div>
      </div>
    </Wrapper>
  )
}

/** A compact one-line variant for dashboard "top categories" lists. */
export interface BudgetProgressCompactProps {
  name: string
  icon: string
  color: string
  spentDisplay: string
  consumedPercent: string | number
  status: BudgetStatus
  statusLabel: string
  elapsedPercent?: string | number
  className?: string
}

export function BudgetProgressCompact({
  name,
  icon,
  color,
  spentDisplay,
  consumedPercent,
  status,
  statusLabel,
  elapsedPercent,
  className = '',
}: BudgetProgressCompactProps) {
  const consumed = Number(consumedPercent || 0)

  return (
    <div className={['flex flex-col gap-2', className].filter(Boolean).join(' ')}>
      <div className="flex items-center gap-2.5">
        <CategoryIcon name={icon} color={color} size="sm" />

        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-2">
            <span className="truncate text-[13px] font-medium text-ink">{name}</span>
            <span className="ltr-nums shrink-0 text-[12px] text-ink-soft">{spentDisplay}</span>
          </div>
        </div>

        <span
          className={[
            'ltr-nums shrink-0 text-[11.5px] font-semibold',
            status === 'over'
              ? 'text-critical-600'
              : status === 'near_limit'
                ? 'text-caution-700'
                : 'text-ink-soft',
          ].join(' ')}
        >
          {formatPercent(consumed)}
        </span>
      </div>

      <ProgressBar
        value={consumed}
        tone={STATUS_TONE[status]}
        size="sm"
        markerPercent={elapsedPercent === undefined ? undefined : Number(elapsedPercent || 0)}
        label={`میزان مصرف بودجه ${name}، ${statusLabel}`}
      />
    </div>
  )
}
