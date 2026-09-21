import type { ReactNode } from 'react'
import { Inbox } from 'lucide-react'

export interface EmptyStateProps {
  icon?: ReactNode
  title: string
  description?: string
  action?: ReactNode
  className?: string
}

/**
 * Shown when a list is genuinely empty (as opposed to still loading).
 *
 * The copy is friendly and non-judgemental, and always offered alongside a
 * way forward, per the product principle in the spec.
 */
export function EmptyState({
  icon,
  title,
  description,
  action,
  className = '',
}: EmptyStateProps) {
  return (
    <div
      className={[
        'flex flex-col items-center justify-center gap-3 px-6 py-12 text-center',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <span className="flex size-14 items-center justify-center rounded-pill bg-surface-muted text-ink-faint [&>svg]:size-6">
        {icon ?? <Inbox aria-hidden="true" />}
      </span>

      <div className="space-y-1">
        <p className="text-[15px] font-semibold text-ink">{title}</p>
        {description ? (
          <p className="mx-auto max-w-xs text-[13px] leading-6 text-ink-faint">{description}</p>
        ) : null}
      </div>

      {action ? <div className="pt-1">{action}</div> : null}
    </div>
  )
}
