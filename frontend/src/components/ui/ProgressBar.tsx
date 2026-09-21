export type ProgressTone = 'positive' | 'caution' | 'critical' | 'info' | 'brand' | 'neutral'

export interface ProgressBarProps {
  /** Consumption as a 0-100+ percentage. Values above 100 are clamped visually. */
  value: number
  tone?: ProgressTone
  /** Height of the track. */
  size?: 'sm' | 'md' | 'lg'
  /** A faint marker showing how far through the period we are. */
  markerPercent?: number
  /** Accessible label; the bar is meaningless without one. */
  label: string
  className?: string
}

const TRACK_TONES: Record<ProgressTone, string> = {
  positive: 'bg-positive-100',
  caution: 'bg-caution-100',
  critical: 'bg-critical-100',
  info: 'bg-info-100',
  brand: 'bg-brand-100',
  neutral: 'bg-surface-muted',
}

const FILL_TONES: Record<ProgressTone, string> = {
  positive: 'bg-positive-500',
  caution: 'bg-caution-500',
  critical: 'bg-critical-500',
  info: 'bg-info-500',
  brand: 'bg-brand-500',
  neutral: 'bg-ink-faint',
}

const SIZES = {
  sm: 'h-1.5',
  md: 'h-2',
  lg: 'h-2.5',
} as const

/**
 * A budget consumption bar.
 *
 * When `markerPercent` is supplied the bar also shows where the month itself
 * has got to, which is the whole point of the "is this pace normal?" analysis:
 * the eye compares the filled bar against the marker.
 */
export function ProgressBar({
  value,
  tone = 'brand',
  size = 'md',
  markerPercent,
  label,
  className = '',
}: ProgressBarProps) {
  const clamped = Math.max(0, Math.min(100, value))
  const oversized = value > 100

  return (
    <div
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(clamped)}
      aria-label={label}
      className={[
        'relative w-full overflow-hidden rounded-pill',
        TRACK_TONES[tone],
        SIZES[size],
        className,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <div
        className={[
          'h-full rounded-pill transition-[width] duration-300 ease-out',
          FILL_TONES[tone],
        ].join(' ')}
        style={{ width: `${clamped}%` }}
      />

      {/* Overflow hatch: signals "over budget" without relying on colour. */}
      {oversized ? (
        <div
          className="absolute inset-y-0 end-0 w-1.5 bg-critical-700"
          aria-hidden="true"
        />
      ) : null}

      {markerPercent !== undefined ? (
        // The pace marker must survive any fill tone, so it is a solid light
        // bar with a hairline outline rather than a translucent ink line that
        // disappears against a similarly-shaded track.
        <div
          className="absolute inset-y-0 w-[3px] rounded-pill bg-surface shadow-[0_0_0_1px_rgba(16,18,24,0.35)]"
          style={{ insetInlineStart: `${Math.max(0, Math.min(100, markerPercent))}%` }}
          aria-hidden="true"
        />
      ) : null}
    </div>
  )
}
