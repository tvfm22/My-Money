import type { ReactNode } from 'react'

type Variant = 'positive' | 'caution' | 'critical' | 'info' | 'neutral' | 'brand'
type Size = 'sm' | 'md'

export interface BadgeProps {
  variant?: Variant
  size?: Size
  icon?: ReactNode
  children: ReactNode
  className?: string
}

// Backed by the design tokens in index.css. Note that every badge ships with
// a text label as well as a colour — the spec forbids colour as the sole
// carrier of information.
const VARIANTS: Record<Variant, string> = {
  positive: 'bg-positive-50 text-positive-700',
  caution: 'bg-caution-50 text-caution-700',
  critical: 'bg-critical-50 text-critical-700',
  info: 'bg-info-50 text-info-600',
  brand: 'bg-brand-50 text-brand-700',
  neutral: 'bg-surface-muted text-ink-soft',
}

const SIZES: Record<Size, string> = {
  sm: 'h-6 px-2 text-[11px] gap-1',
  md: 'h-7 px-2.5 text-xs gap-1.5',
}

export function Badge({
  variant = 'neutral',
  size = 'md',
  icon,
  children,
  className = '',
}: BadgeProps) {
  return (
    <span
      className={[
        'inline-flex items-center rounded-pill font-medium whitespace-nowrap',
        VARIANTS[variant],
        SIZES[size],
        className,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      {icon}
      {children}
    </span>
  )
}
