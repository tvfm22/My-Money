/**
 * A Jalali month navigator: ‹ شهریور 1405 ›
 *
 * Used by every screen that is scoped to a month (dashboard, budgets, reports,
 * insights), so travelling through time works the same way everywhere.
 */
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { JALALI_MONTHS, currentJalaliMonth } from '../../utils/jalali'
import { formatYear } from '../../utils/format'

export interface MonthNavigatorProps {
  year: number
  month: number
  onChange: (year: number, month: number) => void
  /** Disallow moving into the future. */
  maxYear?: number
  maxMonth?: number
  /**
   * Let the user move past the current month.
   *
   * Off by default: a screen showing *actual* activity (dashboard, reports)
   * has nothing to say about a month that has not happened, and an empty
   * forward month reads as "your data disappeared".
   *
   * On for screens that describe a *plan* rather than a record — budgets are
   * set in advance, so the user has to be able to reach next month to fill it
   * in. Forward navigation is then bounded by `futureMonths` so the control
   * cannot run away to 1410.
   */
  allowFuture?: boolean
  /** How far ahead `allowFuture` reaches. Ignored when `allowFuture` is false. */
  futureMonths?: number
  className?: string
}

/** Advance a Jalali year/month pair by `delta` months, rolling the year over. */
function shiftMonth(year: number, month: number, delta: number): [number, number] {
  let nextMonth = month + delta
  let nextYear = year
  if (nextMonth < 1) {
    nextMonth = 12
    nextYear -= 1
  } else if (nextMonth > 12) {
    nextMonth = 1
    nextYear += 1
  }
  return [nextYear, nextMonth]
}

export function MonthNavigator({
  year,
  month,
  onChange,
  maxYear,
  maxMonth,
  allowFuture = false,
  futureMonths = 12,
  className = '',
}: MonthNavigatorProps) {
  const today = currentJalaliMonth()

  // The furthest month this control may reach. With `allowFuture` the ceiling
  // is a year out, which covers annual planning without turning the navigator
  // into an unbounded time machine.
  const [defaultLimitYear, defaultLimitMonth] = allowFuture
    ? shiftMonth(today.year, today.month, futureMonths)
    : [today.year, today.month]

  const limitYear = maxYear ?? defaultLimitYear
  const limitMonth = maxMonth ?? defaultLimitMonth

  const atLimit = year > limitYear || (year === limitYear && month >= limitMonth)
  const isCurrent = year === today.year && month === today.month
  const isFuture = year > today.year || (year === today.year && month > today.month)

  const step = (delta: number) => {
    onChange(...shiftMonth(year, month, delta))
  }

  return (
    <div
      className={[
        'flex items-center justify-between gap-2 rounded-card border border-border bg-surface px-2 py-1.5',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      {/* In RTL, "previous month" is the button that moves right. */}
      <button
        type="button"
        onClick={() => step(-1)}
        aria-label="ماه قبل"
        className="flex size-11 items-center justify-center rounded-control text-ink-soft transition-colors hover:bg-surface-muted active:bg-surface-muted"
      >
        <ChevronRight className="size-4" aria-hidden="true" />
      </button>

      <div className="flex items-center gap-2">
        <span className="text-[13.5px] font-semibold text-ink">
          {JALALI_MONTHS[month - 1]} {formatYear(year)}
        </span>
        {isCurrent ? (
          <span className="rounded-pill bg-brand-50 px-2 py-0.5 text-[10.5px] font-medium text-brand-700">
            ماه جاری
          </span>
        ) : (
          <>
            {/* A future month must be labelled. Budget screens can reach it,
                and without this badge the plan reads as if it were a record
                of something that already happened. */}
            {isFuture ? (
              <span className="rounded-pill bg-info-50 px-2 py-0.5 text-[10.5px] font-medium text-info-600">
                ماه آینده
              </span>
            ) : null}
            <button
              type="button"
              onClick={() => onChange(today.year, today.month)}
              className="rounded-control px-2 py-0.5 text-[10.5px] font-medium text-brand-600 hover:bg-brand-50"
            >
              بازگشت به ماه جاری
            </button>
          </>
        )}
      </div>

      <button
        type="button"
        onClick={() => step(1)}
        disabled={atLimit}
        aria-label="ماه بعد"
        className="flex size-11 items-center justify-center rounded-control text-ink-soft transition-colors hover:bg-surface-muted active:bg-surface-muted disabled:opacity-40 disabled:hover:bg-transparent"
      >
        <ChevronLeft className="size-4" aria-hidden="true" />
      </button>
    </div>
  )
}
