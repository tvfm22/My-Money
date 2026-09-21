import { forwardRef } from 'react'
import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Loader2 } from 'lucide-react'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'success'
type Size = 'sm' | 'md' | 'lg' | 'icon'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  isLoading?: boolean
  fullWidth?: boolean
  leadingIcon?: ReactNode
  trailingIcon?: ReactNode
  children?: ReactNode
}

const VARIANTS: Record<Variant, string> = {
  primary:
    'bg-brand-600 text-white border-transparent hover:bg-brand-700 active:bg-brand-700 shadow-xs',
  secondary:
    'bg-surface text-ink border-border-strong hover:bg-surface-muted active:bg-surface-muted',
  ghost:
    'bg-transparent text-ink-soft border-transparent hover:bg-surface-muted hover:text-ink',
  danger:
    'bg-critical-500 text-white border-transparent hover:bg-critical-700 active:bg-critical-700',
  success: 'bg-positive-600 text-white border-transparent hover:bg-positive-700',
}

// Touch targets are at least 44px tall on `md`/`lg` so the app stays usable
// one-handed on a phone, which the product spec calls out explicitly.
const SIZES: Record<Size, string> = {
  sm: 'h-9 px-3 text-[13px] gap-1.5 rounded-control',
  md: 'h-11 px-4 text-sm gap-2 rounded-control',
  lg: 'h-12 px-5 text-[15px] gap-2 rounded-control',
  icon: 'h-11 w-11 justify-center rounded-control',
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = 'primary',
    size = 'md',
    isLoading = false,
    fullWidth = false,
    leadingIcon,
    trailingIcon,
    className = '',
    disabled,
    children,
    ...rest
  },
  ref,
) {
  const classes = [
    // `justify-center` is not decoration: the base is `inline-flex`, so without
    // it a `fullWidth` button packs its label against the start edge — which in
    // this RTL layout means the right edge. Every full-width submit button was
    // showing its label hard right instead of centred. Non-full-width buttons
    // size to their content, so this is invisible there.
    'inline-flex items-center justify-center font-medium transition-colors duration-150',
    'border select-none whitespace-nowrap',
    'disabled:opacity-50 disabled:pointer-events-none',
    VARIANTS[variant],
    SIZES[size],
    fullWidth ? 'w-full' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <button
      ref={ref}
      className={classes}
      disabled={disabled || isLoading}
      aria-busy={isLoading || undefined}
      {...rest}
    >
      {isLoading ? (
        <Loader2 className="size-4 animate-spin shrink-0" aria-hidden="true" />
      ) : (
        leadingIcon
      )}
      {children}
      {!isLoading && trailingIcon}
    </button>
  )
})
