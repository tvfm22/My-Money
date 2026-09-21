import type { HTMLAttributes, ReactNode } from 'react'

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  padded?: boolean
  interactive?: boolean
  children: ReactNode
}

export function Card({
  padded = true,
  interactive = false,
  className = '',
  children,
  ...rest
}: CardProps) {
  return (
    <div
      className={[
        'bg-surface border border-border rounded-card shadow-card',
        padded ? 'p-4 sm:p-5' : '',
        interactive
          ? 'transition-shadow duration-150 hover:shadow-raised cursor-pointer'
          : '',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
      {...rest}
    >
      {children}
    </div>
  )
}

export interface CardHeaderProps {
  title: ReactNode
  subtitle?: ReactNode
  action?: ReactNode
  className?: string
}

export function CardHeader({ title, subtitle, action, className = '' }: CardHeaderProps) {
  return (
    <div className={['flex items-start justify-between gap-3', className].filter(Boolean).join(' ')}>
      <div className="min-w-0">
        <h2 className="text-[15px] font-semibold text-ink">{title}</h2>
        {subtitle ? <p className="mt-0.5 text-xs text-ink-faint">{subtitle}</p> : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  )
}
