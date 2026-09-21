import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { CalendarDays, ChevronLeft, ChevronRight } from 'lucide-react'
import {
  JALALI_MONTHS,
  JALALI_WEEKDAYS_SHORT,
  addJalaliMonths,
  formatJalali,
  jalaliMonthGrid,
  jalaliToIso,
  toJalali,
} from '../../utils/jalali'
import { formatDigits, formatYear } from '../../utils/format'

export interface JalaliDatePickerProps {
  /** ISO (Gregorian) date string, e.g. "2026-09-20". This is what gets stored. */
  value: string
  /** Receives an ISO (Gregorian) date string, never a Jalali one. */
  onChange: (iso: string) => void
  label?: string
  error?: string
  hint?: string
  /** Days after today are disabled. Transaction dates cannot be in the future. */
  disableFuture?: boolean
  placeholder?: string
  id?: string
  /** Rendered inline instead of in a popover — used inside sheets on mobile. */
  inline?: boolean
}

const WEEKDAY_HEADERS = JALALI_WEEKDAYS_SHORT

/**
 * A Jalali (Solar Hijri) date picker.
 *
 * This is a real Persian calendar picker, not a Gregorian input with Persian
 * digits: the year/month/day fields, the weekday order (شنبه first), and the
 * month lengths all follow the Jalali calendar. The value crossing the
 * component boundary is always ISO Gregorian, so the component is safe to
 * wire straight into a form and post to the API.
 */
export function JalaliDatePicker({
  value,
  onChange,
  label,
  error,
  hint,
  disableFuture = false,
  placeholder = 'انتخاب تاریخ',
  id,
  inline = false,
}: JalaliDatePickerProps) {
  const [open, setOpen] = useState(inline)
  const containerRef = useRef<HTMLDivElement>(null)

  // The month currently being *browsed*, which is independent of the selected
  // date so the user can page around without losing their choice.
  const selectedJalali = useMemo(() => (value ? toJalali(value) : null), [value])
  const [cursor, setCursor] = useState(() => {
    const base = selectedJalali ?? toJalali(new Date())
    return { year: base.year, month: base.month }
  })

  // Follow the value when it changes from outside (e.g. a form reset).
  useEffect(() => {
    if (selectedJalali) {
      setCursor({ year: selectedJalali.year, month: selectedJalali.month })
    }
    // Only react to the selected month, not to every render.
  }, [selectedJalali?.year, selectedJalali?.month])

  useEffect(() => {
    if (inline || !open) return

    const onPointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }

    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open, inline])

  const grid = useMemo(() => jalaliMonthGrid(cursor.year, cursor.month), [cursor.year, cursor.month])

  // Resolved once per render: today in ISO, used for the "today" affordance
  // and for the future-date guard.
  const realTodayIso = useMemo(() => {
    const today = toJalali(new Date())
    return jalaliToIso(today.year, today.month, today.day)
  }, [])

  // A hardcoded fallback (`'jalali-date'`) meant a form with two pickers — a
  // debt has both an issue date and a due date — emitted the same DOM id
  // twice. Both labels then pointed at the first button, so the second one was
  // unlabelled for screen readers and `getByLabelText('تاریخ سررسید')` resolved
  // to the wrong control. `useId()` keeps every instance unique.
  const generatedId = useId()
  const inputId = id ?? `jalali-date-${generatedId}`
  const errorId = error ? `${inputId}-error` : undefined

  const displayValue = value ? formatJalali(value, 'long') : ''

  const pick = (iso: string) => {
    onChange(iso)
    if (!inline) setOpen(false)
  }

  const goToMonth = (delta: number) => {
    setCursor((current) => addJalaliMonths(current.year, current.month, delta))
  }

  const isDisabled = (iso: string) => disableFuture && iso > realTodayIso

  const yearOptions = useMemo(() => {
    const base = cursor.year
    const years: number[] = []
    for (let y = base - 8; y <= base + 4; y += 1) years.push(y)
    return years
  }, [cursor.year])

  const calendar = (
    <div className="w-full rounded-card border border-border bg-surface p-3 shadow-card">
      {/* Month / year controls */}
      <div className="mb-3 flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => goToMonth(-1)}
          aria-label="ماه قبل"
          className="flex size-9 items-center justify-center rounded-control text-ink-soft transition-colors hover:bg-surface-muted"
        >
          <ChevronRight className="size-4" aria-hidden="true" />
        </button>

        <div className="flex items-center gap-1.5">
          <select
            aria-label="ماه"
            value={cursor.month}
            onChange={(event) =>
              setCursor((current) => ({ ...current, month: Number(event.target.value) }))
            }
            className="h-9 rounded-control border border-border-strong bg-surface px-2 text-[13px] font-medium text-ink"
          >
            {JALALI_MONTHS.map((name, index) => (
              <option key={name} value={index + 1}>
                {name}
              </option>
            ))}
          </select>

          <select
            aria-label="سال"
            value={cursor.year}
            onChange={(event) =>
              setCursor((current) => ({ ...current, year: Number(event.target.value) }))
            }
            className="h-9 rounded-control border border-border-strong bg-surface px-2 text-[13px] font-medium text-ink ltr-nums"
          >
            {yearOptions.map((year) => (
              <option key={year} value={year}>
                {formatYear(year)}
              </option>
            ))}
          </select>
        </div>

        <button
          type="button"
          onClick={() => goToMonth(1)}
          aria-label="ماه بعد"
          className="flex size-9 items-center justify-center rounded-control text-ink-soft transition-colors hover:bg-surface-muted"
        >
          <ChevronLeft className="size-4" aria-hidden="true" />
        </button>
      </div>

      {/* Weekday header — Jalali weeks start on شنبه. */}
      <div className="mb-1 grid grid-cols-7 gap-1">
        {WEEKDAY_HEADERS.map((day) => (
          <span key={day} className="text-center text-[11px] font-medium text-ink-faint">
            {day}
          </span>
        ))}
      </div>

      <div className="grid grid-cols-7 gap-1">
        {grid.map((cell) => {
          const isSelected = value === cell.iso
          const isToday = cell.iso === realTodayIso
          const disabled = isDisabled(cell.iso)

          return (
            <button
              key={cell.iso}
              type="button"
              disabled={disabled}
              onClick={() => pick(cell.iso)}
              aria-current={isSelected ? 'date' : undefined}
              aria-label={formatJalali(cell.iso, 'full')}
              className={[
                'flex h-9 items-center justify-center rounded-control text-[13px] transition-colors',
                'ltr-nums',
                disabled ? 'cursor-not-allowed text-ink-faint/50' : '',
                !disabled && !isSelected ? 'hover:bg-surface-muted' : '',
                !cell.inMonth && !isSelected ? 'text-ink-faint/60' : 'text-ink',
                isSelected ? 'bg-brand-600 font-semibold text-white' : '',
                !isSelected && isToday ? 'ring-1 ring-brand-300 ring-inset font-medium' : '',
              ]
                .filter(Boolean)
                .join(' ')}
            >
              {formatDigits(cell.jalali.day)}
            </button>
          )
        })}
      </div>

      <div className="mt-3 flex items-center justify-between border-t border-border pt-3">
        <button
          type="button"
          onClick={() => {
            setCursor(toJalali(new Date()))
          }}
          className="text-xs font-medium text-brand-600 hover:text-brand-700"
        >
          ماه جاری
        </button>

        <button
          type="button"
          disabled={disableFuture}
          onClick={() => pick(realTodayIso)}
          className={[
            'rounded-control px-2.5 py-1 text-xs font-medium transition-colors',
            disableFuture
              ? 'cursor-not-allowed text-ink-faint'
              : 'text-brand-600 hover:bg-brand-50',
          ]
            .filter(Boolean)
            .join(' ')}
        >
          امروز
        </button>
      </div>
    </div>
  )

  if (inline) {
    return (
      <div className="flex flex-col gap-1.5">
        {label ? <span className="text-[13px] font-medium text-ink-soft">{label}</span> : null}
        {calendar}
      </div>
    )
  }

  return (
    <div ref={containerRef} className="relative flex flex-col gap-1.5">
      {label ? (
        <label htmlFor={inputId} className="text-[13px] font-medium text-ink-soft">
          {label}
        </label>
      ) : null}

      <button
        id={inputId}
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-invalid={error ? true : undefined}
        aria-describedby={errorId}
        className={[
          'flex h-11 w-full items-center justify-between gap-2 rounded-control border bg-surface px-3 text-sm',
          'transition-colors duration-150 text-start',
          error ? 'border-critical-500' : 'border-border-strong hover:border-brand-300',
        ]
          .filter(Boolean)
          .join(' ')}
      >
        <span className={displayValue ? 'text-ink' : 'text-ink-faint'}>
          {displayValue || placeholder}
        </span>
        <CalendarDays className="size-4 shrink-0 text-ink-faint" aria-hidden="true" />
      </button>

      {error ? (
        <p id={errorId} role="alert" className="text-xs text-critical-600">
          {error}
        </p>
      ) : hint ? (
        <p className="text-xs text-ink-faint">{hint}</p>
      ) : null}

      {open ? (
        <div
          role="dialog"
          aria-label={label ? `انتخاب ${label}` : 'انتخاب تاریخ'}
          className="absolute top-full z-40 mt-2 w-[19rem] animate-fade-rise end-0"
        >
          {calendar}
        </div>
      ) : null}
    </div>
  )
}
