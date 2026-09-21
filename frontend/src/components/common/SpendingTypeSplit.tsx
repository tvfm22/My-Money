import { ProgressBar } from '../ui/ProgressBar'
import { formatDigits } from '../../utils/format'
import type { ProgressTone } from '../ui/ProgressBar'
import type { SpendingTypes } from '../../types'

/**
 * Server keys → visual tone. The labels come from the server, so the mapping
 * only decides how a slice is painted — and a key the server adds later
 * simply falls back to neutral rather than crashing.
 */
const TONE_BY_KEY: Record<string, ProgressTone> = {
  essential: 'brand',
  flexible: 'info',
  wasted: 'caution',
}

export interface SpendingTypeSplitProps {
  spendingTypes: SpendingTypes
  className?: string
}

/**
 * The essential / flexible / wasted split as plain rows — bar, amount, share.
 *
 * Deliberately a list rather than a chart: three numbers with names don't
 * need a legend, and the row keeps every figure labelled and readable in
 * both themes.
 */
export function SpendingTypeSplit({ spendingTypes, className = '' }: SpendingTypeSplitProps) {
  return (
    <ul className={['space-y-3.5', className].filter(Boolean).join(' ')}>
      {spendingTypes.buckets.map((bucket) => (
        <li key={bucket.key}>
          <div className="mb-1.5 flex items-baseline justify-between gap-2">
            <span className="text-[12.5px] text-ink-soft">
              {bucket.label}
              <span className="text-ink-faint">
                {' ('}
                <span className="ltr-nums">{formatDigits(bucket.transaction_count)}</span>
                {' تراکنش)'}
              </span>
            </span>
            <span className="flex items-center gap-2">
              <span className="ltr-nums text-[12.5px] font-medium text-ink">
                {bucket.amount_display}
              </span>
              <span className="ltr-nums text-[11px] text-ink-faint">
                {bucket.share_display}
              </span>
            </span>
          </div>
          <ProgressBar
            value={Number(bucket.share_percent || 0)}
            tone={TONE_BY_KEY[bucket.key] ?? 'brand'}
            size="sm"
            label={`${bucket.label}: ${bucket.amount_display} (${bucket.share_display})`}
          />
        </li>
      ))}
    </ul>
  )
}
