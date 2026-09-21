import { forwardRef, useId } from 'react'
import type { InputHTMLAttributes, ReactNode } from 'react'

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  hint?: string
  error?: string
  leadingIcon?: ReactNode
  trailingSlot?: ReactNode
  containerClassName?: string
}

/**
 * A text/number input with a label, optional hint, and error state.
 *
 * The label is always associated with the control, and the error message is
 * wired through `aria-describedby` and `aria-invalid` so a screen reader
 * announces the problem rather than relying on the red border alone.
 *
 * The id falls back to a generated one rather than to `name`, because not every
 * caller passes a `name` — previously such an input rendered a `<label>` pointing
 * at nothing, which silently breaks both label-click focus and screen-reader
 * announcement.
 */
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  {
    label,
    hint,
    error,
    leadingIcon,
    trailingSlot,
    containerClassName = '',
    className = '',
    id,
    ...rest
  },
  ref,
) {
  const generatedId = useId()
  const inputId = id ?? rest.name ?? `input-${generatedId}`
  const hintId = hint ? `${inputId}-hint` : undefined
  const errorId = error ? `${inputId}-error` : undefined
  const describedBy = [errorId, hintId].filter(Boolean).join(' ') || undefined

  return (
    <div className={['flex flex-col gap-1.5', containerClassName].filter(Boolean).join(' ')}>
      {label ? (
        <label htmlFor={inputId} className="text-[13px] font-medium text-ink-soft">
          {label}
        </label>
      ) : null}

      <div className="relative">
        {leadingIcon ? (
          <span
            className="pointer-events-none absolute inset-y-0 end-3 flex items-center text-ink-faint [&>svg]:size-4"
            aria-hidden="true"
          >
            {leadingIcon}
          </span>
        ) : null}

        <input
          ref={ref}
          id={inputId}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={[
            'h-11 w-full rounded-control border bg-surface px-3 text-sm text-ink',
            'transition-colors duration-150',
            'placeholder:text-ink-faint',
            'disabled:bg-surface-muted disabled:text-ink-faint',
            leadingIcon ? 'pe-10' : '',
            trailingSlot ? 'ps-12' : '',
            error
              ? 'border-critical-500 focus:border-critical-500'
              : 'border-border-strong focus:border-brand-500',
            className,
          ]
            .filter(Boolean)
            .join(' ')}
          {...rest}
        />

        {trailingSlot ? (
          <span className="absolute inset-y-0 start-2 flex items-center">{trailingSlot}</span>
        ) : null}
      </div>

      {error ? (
        <p id={errorId} role="alert" className="text-xs text-critical-600">
          {error}
        </p>
      ) : hint ? (
        <p id={hintId} className="text-xs text-ink-faint">
          {hint}
        </p>
      ) : null}
    </div>
  )
})
