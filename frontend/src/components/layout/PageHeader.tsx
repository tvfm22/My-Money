/**
 * The header strip at the top of every page: a Jalali month, a title, and an
 * optional action. Kept as a component so all pages share the same rhythm.
 */
import type { ReactNode } from 'react'

export interface PageHeaderProps {
  title: string
  subtitle?: ReactNode
  action?: ReactNode
  className?: string
}

export function PageHeader({ title, subtitle, action, className = '' }: PageHeaderProps) {
  return (
    <header
      className={['mb-4 flex items-start justify-between gap-3 lg:mb-6', className]
        .filter(Boolean)
        .join(' ')}
    >
      <div className="min-w-0">
        <h1 className="text-lg font-bold text-ink lg:text-xl">{title}</h1>
        {subtitle ? (
          <p className="mt-1 text-[12.5px] leading-5 text-ink-soft">{subtitle}</p>
        ) : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </header>
  )
}
