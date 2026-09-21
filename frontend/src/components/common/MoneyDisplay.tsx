import type { ReactNode } from 'react'
import { formatMoney, formatMoneyCompact, formatPercentChange } from '../../utils/format'

export interface MoneyDisplayProps {
  /** Amount as returned by the API: a decimal string, e.g. "1500000.00". */
  value: string | number | null | undefined
  /** Prefix a `+` for positive values and rely on the sign for negatives. */
  signed?: boolean
  /** Render with a compact scale (میلیون / میلیارد) for dense cards. */
  compact?: boolean
  /** Append the currency unit. Defaults to true. */
  withUnit?: boolean
  /** Colour the number by direction: green for positive, red for negative. */
  coloured?: boolean
  /** Treat a positive value as "bad" (e.g. a growing debt). */
  invertColour?: boolean
  className?: string
}

/**
 * Renders a monetary amount with the product's numeral style, isolated LTR so
 * it never visually reorders inside an RTL line.
 *
 * Never formatted with `Intl` here — `Intl`'s `fa-IR` output puts the unit in
 * the wrong place and varies between browsers. `formatMoney` is explicit.
 *
 * Note this takes the *raw* amount, not a server `*_display` string, so the
 * numeral style stays under client control in one place.
 */
export function MoneyDisplay({
  value,
  signed = false,
  compact = false,
  withUnit = true,
  coloured = false,
  invertColour = false,
  className = '',
}: MoneyDisplayProps) {
  // `formatMoneyCompact` already omits the unit by design — it is meant for
  // chart axes and dense cards where "تومان" would be noise.
  const rendered = compact
    ? formatMoneyCompact(value)
    : formatMoney(value, { withUnit })

  const numeric =
    value === null || value === undefined || value === ''
      ? 0
      : typeof value === 'number'
        ? value
        : Number(value.replace(/[^\d.-]/g, '')) || 0

  let colour = ''
  if (coloured && numeric !== 0) {
    const isGood = invertColour ? numeric < 0 : numeric > 0
    colour = isGood ? 'text-positive-600' : 'text-critical-600'
  }

  const showSign = signed && numeric > 0

  return (
    <span className={['ltr-nums tabular-nums', colour, className].filter(Boolean).join(' ')}>
      {showSign ? <span aria-hidden="true">+</span> : null}
      {rendered}
    </span>
  )
}

export interface MoneyDeltaProps {
  /** Current-period value. */
  current: string | number | null | undefined
  /** Previous-period value used to compute the percentage change. */
  previous: string | number | null | undefined
  /** Label shown after the percentage, e.g. "نسبت به ماه قبل". */
  label?: ReactNode
  className?: string
}

/** A percentage change chip used on comparison cards and insight rows. */
export function MoneyDelta({ current, previous, label, className = '' }: MoneyDeltaProps) {
  const a = Number(current ?? 0)
  const b = Number(previous ?? 0)
  if (!b) return null

  const percent = ((a - b) / Math.abs(b)) * 100
  const up = percent > 0
  const flat = Math.abs(percent) < 0.5

  return (
    <span
      className={[
        'inline-flex items-center gap-1 text-xs font-medium',
        flat ? 'text-ink-faint' : up ? 'text-critical-600' : 'text-positive-600',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <span className="ltr-nums">{formatPercentChange(percent)}</span>
      {label ? <span className="text-ink-faint font-normal">{label}</span> : null}
    </span>
  )
}
