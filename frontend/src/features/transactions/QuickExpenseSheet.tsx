import { useEffect, useMemo, useState } from 'react'
import { Check, Delete } from 'lucide-react'
import { ResponsiveDialog } from '../../components/ui/ResponsiveDialog'
import { Button } from '../../components/ui/Button'
import { useToast } from '../../components/ui/Toast'
import { CategoryIcon } from '../../components/common/CategoryIcon'
import { SpendingTypeSelector } from '../../components/common/SpendingTypeSelector'
import { JalaliDatePicker } from '../../components/ui/JalaliDatePicker'
import { useCategoryPicker, useCreateTransaction } from '../../hooks/queries'
import { useAuth } from '../../hooks/useAuth'
import { errorMessage } from '../../services/client'
import {
  USE_PERSIAN_DIGITS,
  ZERO_PLACEHOLDER,
  formatMoney,
  normalizeNumericInput,
  toPersianDigits,
} from '../../utils/format'
import { currentJalaliMonth, jalaliToIso } from '../../utils/jalali'
import type { CategoryKind, CategoryPickerItem, SpendingType } from '../../types'

const FREQUENT_KEY = 'mymoney.frequent-categories'

/**
 * Remembers the categories a user reaches for most, so the quick-entry sheet
 * opens with the right chips already on screen.
 */
function readFrequent(): number[] {
  try {
    const raw = window.localStorage.getItem(FREQUENT_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.filter((v): v is number => typeof v === 'number') : []
  } catch {
    return []
  }
}

function rememberFrequent(categoryId: number): void {
  try {
    const current = readFrequent().filter((id) => id !== categoryId)
    current.unshift(categoryId)
    window.localStorage.setItem(FREQUENT_KEY, JSON.stringify(current.slice(0, 6)))
  } catch {
    // A full or disabled localStorage must never break recording an expense.
  }
}

export interface QuickExpenseSheetProps {
  open: boolean
  onClose: () => void
}

/**
 * The one-screen expense recorder.
 *
 * Deliberately minimal: amount, category, date, an optional note. Everything
 * else (account, tags) is reachable from the full transaction form. The keypad
 * is in-app rather than the OS keyboard so it opens instantly and shows the
 * grouped Persian amount as it is typed.
 */
export function QuickExpenseSheet({ open, onClose }: QuickExpenseSheetProps) {
  const { user } = useAuth()
  const { showToast } = useToast()
  const [kind, setKind] = useState<CategoryKind>('expense')
  const [amount, setAmount] = useState('')
  const [categoryId, setCategoryId] = useState<number | null>(null)
  const [spendingType, setSpendingType] = useState<SpendingType>('flexible')
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)

  const today = useMemo(() => {
    const now = new Date()
    const jalali = currentJalaliMonth()
    void now
    return jalaliToIso(jalali.year, jalali.month, now.getDate())
  }, [])
  const [occurredOn, setOccurredOn] = useState(today)

  const { data: categories } = useCategoryPicker(kind)
  const createTransaction = useCreateTransaction()

  const frequentIds = useMemo(() => readFrequent(), [open])

  // Reset the date to *today* each time the sheet opens, so a sheet left open
  // across midnight is still correct.
  useEffect(() => {
    if (!open) return
    setOccurredOn(today)
  }, [open, today])

  // Auto-select the most-used category, falling back to the first available.
  useEffect(() => {
    if (!categories || categories.length === 0) return
    if (categoryId && categories.some((c) => c.id === categoryId)) return

    const preferred = categories.find((c) => frequentIds.includes(c.id))
    setCategoryId(preferred?.id ?? categories[0].id)
  }, [categories, categoryId, frequentIds])

  useEffect(() => {
    if (!open) {
      setAmount('')
      setNote('')
      setError(null)
      setKind('expense')
      setSpendingType('flexible')
    }
  }, [open])

  const numericAmount = Number(normalizeNumericInput(amount)) || 0

  const orderedCategories: CategoryPickerItem[] = useMemo(() => {
    if (!categories) return []
    const rank = (c: CategoryPickerItem) => {
      const index = frequentIds.indexOf(c.id)
      return index === -1 ? 999 : index
    }
    return [...categories].sort((a, b) => {
      const delta = rank(a) - rank(b)
      if (delta !== 0) return delta
      return a.name.localeCompare(b.name, 'fa')
    })
  }, [categories, frequentIds])

  const keypad: Array<string | 'del'> = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '000', '0', 'del']

  // Keypad captions are digit *characters*, not quantities: the `000` key has
  // to stay three glyphs wide, and routing it through a number formatter would
  // collapse it to a single `0` and give two keys the same accessible name.
  // Converting character-by-character keeps the label honest and still follows
  // the product-wide numeral style.
  const keypadLabel = (key: string) =>
    USE_PERSIAN_DIGITS ? toPersianDigits(key) : key

  const press = (key: string | 'del') => {
    setError(null)
    if (key === 'del') {
      setAmount((current) => current.slice(0, -1))
      return
    }
    setAmount((current) => {
      const next = `${current}${key}`
      // Guard against absurd amounts and leading zeros.
      if (next.length > 15) return current
      return next.replace(/^0+(?=\d)/, '')
    })
  }

  const submit = () => {
    if (numericAmount <= 0) {
      setError('مبلغ را وارد کنید.')
      return
    }
    if (!categoryId) {
      setError('دسته‌بندی را انتخاب کنید.')
      return
    }

    createTransaction.mutate(
      {
        transaction_type: kind,
        amount: String(numericAmount),
        category: categoryId,
        occurred_on: occurredOn,
        description: note.trim(),
        // Only expenses carry a classification; the server rejects the field
        // on income.
        ...(kind === 'expense' ? { spending_type: spendingType } : {}),
      },
      {
        onSuccess: () => {
          rememberFrequent(categoryId)
          showToast({
            message:
              kind === 'income' ? 'درآمد ثبت شد.' : 'هزینه ثبت شد.',
          })
          onClose()
        },
        onError: (err) => setError(errorMessage(err, 'ثبت تراکنش انجام نشد. دوباره تلاش کنید.')),
      },
    )
  }

  return (
    <ResponsiveDialog
      open={open}
      onClose={onClose}
      title="ثبت سریع تراکنش"
      footer={
        <div className="flex gap-2">
          <Button variant="ghost" onClick={onClose} className="flex-1">
            انصراف
          </Button>
          <Button
            onClick={submit}
            isLoading={createTransaction.isPending}
            className="flex-[2]"
            leadingIcon={<Check className="size-4" aria-hidden="true" />}
          >
            ثبت
          </Button>
        </div>
      }
    >
      <div className="space-y-5">
        {/* Income / expense toggle */}
        <div className="grid grid-cols-2 gap-2 rounded-control bg-surface-muted p-1">
          {(['expense', 'income'] as const).map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => {
                setKind(option)
                setCategoryId(null)
              }}              aria-pressed={kind === option}
              className={[
                'h-10 rounded-control text-[13px] font-medium transition-colors',
                kind === option
                  ? option === 'expense'
                    ? 'bg-surface text-critical-600 shadow-card'
                    : 'bg-surface text-positive-600 shadow-card'
                  : 'text-ink-soft hover:text-ink',
              ].join(' ')}
            >
              {option === 'expense' ? 'هزینه' : 'درآمد'}
            </button>
          ))}
        </div>

        {/* Amount readout */}
        <div className="rounded-card border border-border bg-surface-muted/50 px-4 py-3 text-center">
          <p className="text-[11.5px] text-ink-faint">مبلغ</p>
          <p
            className={[
              'ltr-nums mt-1 text-2xl font-bold tracking-tight',
              numericAmount > 0 ? 'text-ink' : 'text-ink-faint',
            ].join(' ')}
          >
            {numericAmount > 0 ? formatMoney(amount, { withUnit: false }) : ZERO_PLACEHOLDER}
          </p>
          <p className="mt-0.5 text-[11px] text-ink-faint">تومان</p>
        </div>

        {/* Keypad */}
        <div className="grid grid-cols-3 gap-2">
          {keypad.map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => press(key)}
              // The label must match what is on the key. Keypad labels are the
              // digit *characters* themselves, not quantities, so they are
              // converted glyph-by-glyph — `formatDigits` would parse `"000"`
              // as the number 0 and label that key `"0"`, colliding with the
              // real `"0"` key. Both the label and the glyph come from
              // `keypadLabel`, so they cannot drift apart.
              aria-label={key === 'del' ? 'حذف رقم' : keypadLabel(key)}
              className="flex h-12 items-center justify-center rounded-control border border-border bg-surface text-lg font-medium text-ink transition-colors hover:bg-surface-muted active:bg-surface-muted"
            >
              {key === 'del' ? (
                <Delete className="size-5" aria-hidden="true" />
              ) : (
                <span className="ltr-nums">{keypadLabel(key)}</span>
              )}
            </button>
          ))}
        </div>

        {/* Category chips */}
        <div>
          <p className="mb-2 text-[13px] font-medium text-ink-soft">دسته‌بندی</p>
          {orderedCategories.length === 0 ? (
            <p className="text-xs text-ink-faint">در حال بارگذاری دسته‌بندی‌ها…</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {orderedCategories.map((category) => {
                const active = categoryId === category.id
                return (
                  <button
                    key={category.id}
                    type="button"
                    onClick={() => {
                      setCategoryId(category.id)
                      setError(null)
                    }}
                    aria-pressed={active}
                    className={[
                      'flex items-center gap-2 rounded-pill border px-3 py-2 text-[12.5px] transition-colors active:bg-surface-muted',
                      active
                        ? 'border-brand-500 bg-brand-50 text-brand-700 font-medium'
                        : 'border-border bg-surface text-ink-soft hover:border-border-strong',
                    ].join(' ')}
                  >
                    <CategoryIcon
                      name={category.icon}
                      color={category.color}
                      size="sm"
                      filled={false}
                    />
                    {category.name}
                  </button>
                )
              })}
            </div>
          )}
        </div>

        {/* Spending classification — expenses only */}
        {kind === 'expense' ? (
          <div>
            <p className="mb-2 text-[13px] font-medium text-ink-soft">نوع هزینه</p>
            <SpendingTypeSelector
              name="quick-spending-type"
              value={spendingType}
              onChange={setSpendingType}
            />
          </div>
        ) : null}

        {/* Date + note */}
        <div className="grid gap-4 sm:grid-cols-2">
          <JalaliDatePicker
            label="تاریخ"
            value={occurredOn}
            onChange={setOccurredOn}
            disableFuture
          />

          <div className="flex flex-col gap-1.5">
            <label htmlFor="quick-note" className="text-[13px] font-medium text-ink-soft">
              توضیح <span className="font-normal text-ink-faint">(اختیاری)</span>
            </label>
            <input
              id="quick-note"
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="مثلاً ناهار با همکاران"
              className="h-11 rounded-control border border-border-strong bg-surface px-3 text-sm text-ink placeholder:text-ink-faint focus:border-brand-500"
            />
          </div>
        </div>

        {error ? (
          <p role="alert" className="rounded-control bg-critical-50 px-3 py-2 text-xs text-critical-700">
            {error}
          </p>
        ) : null}

        <p className="text-[11px] leading-5 text-ink-faint">
          {user?.display_name ? `${user.display_name} عزیز، ` : ''}
          می‌توانید جزئیات بیشتر مثل حساب و برچسب را بعداً از صفحه تراکنش‌ها ویرایش کنید.
        </p>
      </div>
    </ResponsiveDialog>
  )
}
