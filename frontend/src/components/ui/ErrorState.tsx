import type { ReactNode } from 'react'
import { AlertTriangle, RefreshCw, WifiOff } from 'lucide-react'
import { Button } from './Button'

export interface ErrorStateProps {
  title?: string
  /** A Persian, human-readable explanation. Never a raw status code. */
  message?: string
  onRetry?: () => void
  isRetrying?: boolean
  /** Rendered as a smaller inline block rather than a full-page panel. */
  compact?: boolean
  icon?: ReactNode
  className?: string
}

/**
 * The single place API failures are rendered.
 *
 * The spec forbids surfacing "500 Internal Server Error" to the user: the API
 * client already normalises those into Persian sentences, and this component
 * presents them calmly with a retry affordance.
 */
export function ErrorState({
  title = 'مشکلی پیش آمد',
  message = 'ارتباط با سرور برقرار نشد. دوباره تلاش کنید.',
  onRetry,
  isRetrying = false,
  compact = false,
  icon,
  className = '',
}: ErrorStateProps) {
  const isOffline =
    typeof navigator !== 'undefined' && navigator.onLine === false

  const fallbackIcon = isOffline ? <WifiOff aria-hidden="true" /> : <AlertTriangle aria-hidden="true" />

  if (compact) {
    return (
      <div
        role="alert"
        className={[
          'flex items-center gap-3 rounded-card border border-critical-100 bg-critical-50 p-4',
          className,
        ]
          .filter(Boolean)
          .join(' ')}
      >
        <span className="flex size-9 shrink-0 items-center justify-center rounded-pill bg-surface text-critical-600 [&>svg]:size-4">
          {icon ?? fallbackIcon}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[13px] font-semibold text-critical-700">{title}</p>
          <p className="mt-0.5 text-xs leading-5 text-critical-600">{message}</p>
        </div>
        {onRetry ? (
          <Button variant="secondary" size="sm" onClick={onRetry} isLoading={isRetrying}>
            تلاش دوباره
          </Button>
        ) : null}
      </div>
    )
  }

  return (
    <div
      role="alert"
      className={[
        'flex flex-col items-center justify-center gap-4 px-6 py-14 text-center',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <span className="flex size-14 items-center justify-center rounded-pill bg-critical-50 text-critical-600 [&>svg]:size-6">
        {icon ?? fallbackIcon}
      </span>

      <div className="space-y-1">
        <p className="text-[15px] font-semibold text-ink">{title}</p>
        <p className="mx-auto max-w-sm text-[13px] leading-6 text-ink-soft">{message}</p>
      </div>

      {onRetry ? (
        <Button
          variant="secondary"
          onClick={onRetry}
          isLoading={isRetrying}
          leadingIcon={<RefreshCw className="size-4" aria-hidden="true" />}
        >
          تلاش دوباره
        </Button>
      ) : null}
    </div>
  )
}
