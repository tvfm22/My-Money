import { forwardRef, useId } from 'react'
import type { SelectHTMLAttributes } from 'react'
import { ChevronDown } from 'lucide-react'

export interface SelectOption {
  value: string
  label: string
  disabled?: boolean
}

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string
  hint?: string
  error?: string
  options: SelectOption[]
  placeholder?: string
  containerClassName?: string
}

/**
 * A styled native `<select>`.
 *
 * Native rather than a custom listbox on purpose: on a phone it opens the OS
 * picker, which is faster and more accessible than anything reimplemented in a
 * div. The id falls back to a generated one rather than to `name`, so the label
 * is always associated with the control even when no `name` is passed.
 */
export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  {
    label,
    hint,
    error,
    options,
    placeholder,
    containerClassName = '',
    className = '',
    id,
    ...rest
  },
  ref,
) {
  const generatedId = useId()
  const selectId = id ?? rest.name ?? `select-${generatedId}`
  const hintId = hint ? `${selectId}-hint` : undefined
  const errorId = error ? `${selectId}-error` : undefined
  const describedBy = [errorId, hintId].filter(Boolean).join(' ') || undefined

  return (
    <div className={['flex flex-col gap-1.5', containerClassName].filter(Boolean).join(' ')}>
      {label ? (
        <label htmlFor={selectId} className="text-[13px] font-medium text-ink-soft">
          {label}
        </label>
      ) : null}

      <div className="relative">
        <select
          ref={ref}
          id={selectId}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={[
            'h-11 w-full appearance-none rounded-control border bg-surface ps-3 pe-9 text-sm text-ink',
            'transition-colors duration-150',
            'disabled:bg-surface-muted disabled:text-ink-faint',
            error
              ? 'border-critical-500 focus:border-critical-500'
              : 'border-border-strong focus:border-brand-500',
            className,
          ]
            .filter(Boolean)
            .join(' ')}
          {...rest}
        >
          {placeholder ? (
            <option value="">{placeholder}</option>
          ) : null}
          {options.map((option) => (
            <option key={option.value} value={option.value} disabled={option.disabled}>
              {option.label}
            </option>
          ))}
        </select>

        <ChevronDown
          className="pointer-events-none absolute inset-y-0 end-3 my-auto size-4 text-ink-faint"
          aria-hidden="true"
        />
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
