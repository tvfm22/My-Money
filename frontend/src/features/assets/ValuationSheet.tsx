import { useEffect, useState } from 'react'
import { Trash2 } from 'lucide-react'
import { ResponsiveDialog } from '../../components/ui/ResponsiveDialog'
import { Button } from '../../components/ui/Button'
import { useToast } from '../../components/ui/Toast'
import { JalaliDatePicker } from '../../components/ui/JalaliDatePicker'
import { useAddValuation, useAssetValuations, useDeleteValuation } from '../../hooks/queries'
import { errorMessage, fieldErrors } from '../../services/client'
import { ZERO_PLACEHOLDER, formatDigits, formatPercent, normalizeNumericInput, toLatinDigits } from '../../utils/format'
import { currentJalaliMonth, jalaliToIso } from '../../utils/jalali'
import type { Asset } from '../../types'

export interface ValuationSheetProps {
  asset: Asset | null
  open: boolean
  onClose: () => void
}

/**
 * Record a new value for a holding, and review the history.
 *
 * Valuations are append-only on the server: each entry is kept, so the growth
 * chart has real history rather than a single mutable number. Only the most
 * recent one drives the asset's current value.
 */
export function ValuationSheet({ asset, open, onClose }: ValuationSheetProps) {
  const [value, setValue] = useState('')
  const [valuedOn, setValuedOn] = useState('')
  const [note, setNote] = useState('')
  const [fieldError, setFieldError] = useState<string | null>(null)
  const [formError, setFormError] = useState<string | null>(null)

  const { data: valuations, isPending } = useAssetValuations(asset?.id ?? 0)
  const addValuation = useAddValuation()
  const deleteValuation = useDeleteValuation()
  const { showToast } = useToast()

  useEffect(() => {
    if (!open || !asset) return
    const { year, month } = currentJalaliMonth()
    setValue(String(Math.round(Number(asset.current_value))))
    setValuedOn(jalaliToIso(year, month, new Date().getDate()))
    setNote('')
    setFieldError(null)
    setFormError(null)
  }, [open, asset])

  if (!asset) return null

  const numericValue = Number(normalizeNumericInput(value)) || 0
  const previous = Number(asset.current_value) || 0
  const delta = numericValue - previous
  const deltaPercent = previous > 0 ? (delta / previous) * 100 : null

  const submit = async () => {
    if (numericValue < 0) {
      setFieldError('ارزش نمی‌تواند منفی باشد.')
      return
    }
    if (!valuedOn) {
      setFieldError('تاریخ را انتخاب کنید.')
      return
    }

    setFieldError(null)
    setFormError(null)

    try {
      await addValuation.mutateAsync({
        assetId: asset.id,
        value: String(numericValue),
        valued_on: valuedOn,
        note: note.trim(),
      })
      showToast({ message: 'ارزش جدید ثبت شد.' })
      onClose()
    } catch (error) {
      const fields = fieldErrors(error)
      const first = Object.values(fields)[0]
      if (first) setFieldError(first)
      else setFormError(errorMessage(error, 'ثبت ارزش انجام نشد. دوباره تلاش کنید.'))
    }
  }

  const history = valuations ?? []

  return (
    <ResponsiveDialog
      open={open}
      onClose={onClose}
      title="به‌روزرسانی ارزش"
      description={asset.name}
      footer={
        <div className="flex gap-2">
          <Button variant="ghost" onClick={onClose} className="flex-1">
            انصراف
          </Button>
          <Button
            onClick={submit}
            isLoading={addValuation.isPending}
            className="flex-[2]"
          >
            ثبت ارزش جدید
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="valuation-value" className="text-[13px] font-medium text-ink-soft">
            ارزش جدید (تومان)
          </label>
          <div className="relative">
            <input
              id="valuation-value"
              inputMode="numeric"
              dir="ltr"
              placeholder={ZERO_PLACEHOLDER}
              value={value ? formatDigits(Number(value)) : ''}
              onChange={(event) => {
                setValue(toLatinDigits(event.target.value).replace(/[^\d]/g, ''))
                setFieldError(null)
              }}
              aria-invalid={fieldError ? true : undefined}
              aria-describedby={fieldError ? 'valuation-value-error' : undefined}
              className={[
                'h-11 w-full rounded-control border bg-surface px-3 pe-14 text-sm text-ink ltr-nums',
                'placeholder:text-ink-faint',
                fieldError ? 'border-critical-500' : 'border-border-strong focus:border-brand-500',
              ].join(' ')}
            />
            <span className="pointer-events-none absolute inset-y-0 end-3 flex items-center text-[11px] text-ink-faint">
              تومان
            </span>
          </div>

          {/* Immediate before/after comparison so a typo is obvious. */}
          {numericValue > 0 && previous > 0 ? (
            <p
              className={[
                'text-[11.5px]',
                delta === 0 ? 'text-ink-faint' : delta > 0 ? 'text-positive-600' : 'text-critical-600',
              ].join(' ')}
            >
              {delta === 0 ? (
                'بدون تغییر نسبت به ارزش فعلی'
              ) : (
                <>
                  {delta > 0 ? 'افزایش ' : 'کاهش '}
                  <span className="ltr-nums font-medium">
                    {formatDigits(Math.abs(Math.round(delta)))}
                  </span>
                  {deltaPercent !== null ? (
                    <>
                      {' ('}
                      <span className="ltr-nums">{formatPercent(deltaPercent, 1)}</span>
                      {')'}
                    </>
                  ) : null}
                  {' نسبت به ارزش فعلی'}
                </>
              )}
            </p>
          ) : null}

          {fieldError ? (
            <p id="valuation-value-error" role="alert" className="text-xs text-critical-600">
              {fieldError}
            </p>
          ) : null}
        </div>

        <JalaliDatePicker
          label="تاریخ ارزش‌گذاری"
          value={valuedOn}
          onChange={setValuedOn}
          disableFuture
        />

        <div className="flex flex-col gap-1.5">
          <label htmlFor="valuation-note" className="text-[13px] font-medium text-ink-soft">
            توضیح <span className="font-normal text-ink-faint">(اختیاری)</span>
          </label>
          <input
            id="valuation-note"
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="مثلاً افزایش قیمت طلا"
            className="h-11 rounded-control border border-border-strong bg-surface px-3 text-sm text-ink placeholder:text-ink-faint focus:border-brand-500"
          />
        </div>

        {/* History */}
        <div className="border-t border-border pt-4">
          <p className="mb-3 text-[13px] font-medium text-ink-soft">تاریخچه ارزش‌گذاری</p>

          {isPending ? (
            <p className="text-xs text-ink-faint">در حال بارگذاری…</p>
          ) : history.length === 0 ? (
            <p className="rounded-control bg-surface-muted px-3 py-2.5 text-[11.5px] leading-5 text-ink-faint">
              هنوز ارزش‌گذاری‌ای ثبت نشده است. با ثبت اولین مورد، روند رشد این دارایی رسم می‌شود.
            </p>
          ) : (
            <ul className="space-y-1.5">
              {[...history]
                .sort((a, b) => b.valued_on.localeCompare(a.valued_on))
                .map((entry) => (
                  <li
                    key={entry.id}
                    className="flex items-center justify-between gap-3 rounded-control bg-surface-muted px-3 py-2"
                  >
                    <div className="min-w-0">
                      <p className="ltr-nums text-[12.5px] font-medium text-ink">
                        {entry.value_display}
                      </p>
                      <p className="mt-0.5 text-[10.5px] text-ink-faint">
                        {entry.valued_on_display}
                        {entry.note ? ` • ${entry.note}` : ''}
                      </p>
                    </div>

                    <button
                      type="button"
                      onClick={() =>
                        deleteValuation.mutate(
                          { assetId: asset.id, valuationId: entry.id },
                          { onSuccess: () => showToast({ message: 'ارزش‌گذاری حذف شد.' }) },
                        )
                      }
                      disabled={deleteValuation.isPending}
                      aria-label="حذف این ارزش‌گذاری"
                      className="flex size-9 shrink-0 items-center justify-center rounded-control text-ink-faint transition-colors hover:bg-critical-50 hover:text-critical-600 disabled:opacity-50"
                    >
                      <Trash2 className="size-3.5" aria-hidden="true" />
                    </button>
                  </li>
                ))}
            </ul>
          )}
        </div>

        {formError ? (
          <p role="alert" className="rounded-control bg-critical-50 px-3 py-2 text-xs text-critical-700">
            {formError}
          </p>
        ) : null}
      </div>
    </ResponsiveDialog>
  )
}
