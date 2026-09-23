import type { SpendingType } from '../../types'

export const SPENDING_TYPE_OPTIONS: Array<{
  key: SpendingType
  label: string
  activeClass: string
}> = [
  {
    key: 'essential',
    label: 'ضروری',
    activeClass: 'border-brand-500 bg-brand-50 text-brand-700',
  },
  {
    key: 'flexible',
    label: 'انعطاف‌پذیر',
    activeClass: 'border-info-500 bg-info-50 text-info-600',
  },
  {
    key: 'wasted',
    label: 'غیرضروری',
    activeClass: 'border-caution-500 bg-caution-50 text-caution-700',
  },
]

export interface SpendingTypeSelectorProps {
  value: SpendingType
  onChange: (value: SpendingType) => void
  name: string
}

/**
 * The essential / flexible / wasted picker, shared by the quick sheet and the
 * full form so both always offer the same three options with the same names.
 *
 * Every option is a real radio input — the whole group is keyboard operable
 * and announced as one labelled choice, which a row of bare buttons is not.
 */
export function SpendingTypeSelector({ value, onChange, name }: SpendingTypeSelectorProps) {
  return (
    <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label="نوع هزینه">
      {SPENDING_TYPE_OPTIONS.map((option) => {
        const active = value === option.key
        return (
          <label
            key={option.key}
            className={[
              'flex h-10 cursor-pointer items-center justify-center rounded-control border text-[12.5px] font-medium transition-colors',
              active
                ? option.activeClass
                : 'border-border-strong bg-surface text-ink-soft hover:bg-surface-muted',
            ].join(' ')}
          >
            <input
              type="radio"
              name={name}
              value={option.key}
              checked={active}
              onChange={() => onChange(option.key)}
              className="sr-only"
            />
            {option.label}
          </label>
        )
      })}
    </div>
  )
}
