import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { ResponsiveDialog } from '../../components/ui/ResponsiveDialog'
import { Button } from '../../components/ui/Button'
import { useToast } from '../../components/ui/Toast'
import { Input } from '../../components/ui/Input'
import { JalaliDatePicker } from '../../components/ui/JalaliDatePicker'
import { useCreateDebt, useUpdateDebt } from '../../hooks/queries'
import { errorMessage, fieldErrors } from '../../services/client'
import { ZERO_PLACEHOLDER, formatDigits, normalizeNumericInput, toLatinDigits } from '../../utils/format'
import { currentJalaliMonth, jalaliToIso } from '../../utils/jalali'
import type { Debt } from '../../types'

const schema = z.object({
  direction: z.enum(['payable', 'receivable']),
  counterparty: z
    .string()
    .min(1, 'نام طرف حساب را وارد کنید.')
    .max(150, 'نام بیش از حد طولانی است.'),
  principal: z
    .string()
    .min(1, 'مبلغ را وارد کنید.')
    .refine((value) => Number(normalizeNumericInput(value)) > 0, {
      message: 'مبلغ باید بیشتر از صفر باشد.',
    }),
  issued_on: z.string().min(1, 'تاریخ را انتخاب کنید.'),
  due_on: z.string().min(1, 'تاریخ سررسید را انتخاب کنید.'),
  description: z.string().max(500, 'توضیحات بیش از حد طولانی است.').optional(),
})

type FormValues = z.infer<typeof schema>

function todayIso(): string {
  const { year, month } = currentJalaliMonth()
  return jalaliToIso(year, month, new Date().getDate())
}

export interface DebtFormProps {
  open: boolean
  debt: Debt | null
  defaultDirection?: 'payable' | 'receivable'
  onClose: () => void
}

/** Create or edit a debt/receivable. */
export function DebtForm({ open, debt, defaultDirection = 'payable', onClose }: DebtFormProps) {
  const isEditing = debt !== null
  const [formError, setFormError] = useState<string | null>(null)
  const { showToast } = useToast()

  const createDebt = useCreateDebt()
  const updateDebt = useUpdateDebt()

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    reset,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      direction: defaultDirection,
      counterparty: '',
      principal: '',
      issued_on: todayIso(),
      due_on: todayIso(),
      description: '',
    },
  })

  const direction = watch('direction')
  const principal = watch('principal')
  const issuedOn = watch('issued_on')
  const dueOn = watch('due_on')

  useEffect(() => {
    if (!open) return
    setFormError(null)

    if (debt) {
      reset({
        direction: debt.direction,
        counterparty: debt.counterparty,
        principal: String(Math.round(Number(debt.principal))),
        issued_on: debt.issued_on,
        due_on: debt.due_on,
        description: debt.description || '',
      })
    } else {
      reset({
        direction: defaultDirection,
        counterparty: '',
        principal: '',
        issued_on: todayIso(),
        due_on: todayIso(),
        description: '',
      })
    }
  }, [open, debt, defaultDirection, reset])

  const numericPrincipal = Number(normalizeNumericInput(principal)) || 0
  const dueBeforeIssued = Boolean(issuedOn && dueOn && dueOn < issuedOn)

  const submit = handleSubmit(async (values) => {
    setFormError(null)

    if (values.due_on < values.issued_on) {
      setError('due_on', { message: 'تاریخ سررسید نمی‌تواند قبل از تاریخ ایجاد باشد.' })
      return
    }

    const payload = {
      direction: values.direction,
      counterparty: values.counterparty.trim(),
      principal: String(Number(normalizeNumericInput(values.principal))),
      issued_on: values.issued_on,
      due_on: values.due_on,
      description: values.description?.trim() ?? '',
    }

    try {
      if (isEditing && debt) {
        await updateDebt.mutateAsync({ id: debt.id, ...payload })
        showToast({ message: 'تغییرات ذخیره شد.' })
      } else {
        await createDebt.mutateAsync(payload)
        showToast({
          message: values.direction === 'payable' ? 'بدهی ثبت شد.' : 'طلب ثبت شد.',
        })
      }
      onClose()
    } catch (error) {
      const fields = fieldErrors(error)
      let matched = false
      for (const [field, message] of Object.entries(fields)) {
        if (field in schema.shape) {
          setError(field as keyof FormValues, { message })
          matched = true
        }
      }
      setFormError(matched ? null : errorMessage(error, 'ذخیره اطلاعات انجام نشد. دوباره تلاش کنید.'))
    }
  })

  return (
    <ResponsiveDialog
      open={open}
      onClose={onClose}
      title={isEditing ? 'ویرایش' : direction === 'payable' ? 'ثبت بدهی' : 'ثبت طلب'}
      footer={
        <div className="flex gap-2">
          <Button variant="ghost" onClick={onClose} className="flex-1">
            انصراف
          </Button>
          <Button onClick={submit} isLoading={isSubmitting} className="flex-[2]">
            {isEditing ? 'ذخیره تغییرات' : 'ثبت'}
          </Button>
        </div>
      }
    >
      <form onSubmit={submit} noValidate className="space-y-4">
        {!isEditing ? (
          <fieldset>
            <legend className="mb-2 text-[13px] font-medium text-ink-soft">نوع</legend>
            <div className="grid grid-cols-2 gap-2">
              {(['payable', 'receivable'] as const).map((option) => (
                <label
                  key={option}
                  className={[
                    'flex h-11 cursor-pointer items-center justify-center rounded-control border text-[13px] font-medium transition-colors',
                    direction === option
                      ? option === 'payable'
                        ? 'border-critical-500 bg-critical-50 text-critical-700'
                        : 'border-positive-500 bg-positive-50 text-positive-700'
                      : 'border-border-strong bg-surface text-ink-soft hover:bg-surface-muted',
                  ].join(' ')}
                >
                  <input
                    type="radio"
                    value={option}
                    className="sr-only"
                    {...register('direction')}
                  />
                  {option === 'payable' ? 'بدهی (می‌پردازم)' : 'طلب (دریافت می‌کنم)'}
                </label>
              ))}
            </div>
          </fieldset>
        ) : null}

        <Input
          label={direction === 'payable' ? 'طلبکار' : 'بدهکار'}
          placeholder={direction === 'payable' ? 'مثلاً بانک ملت' : 'مثلاً آقای رضایی'}
          error={errors.counterparty?.message}
          {...register('counterparty')}
        />

        <Input
          label="مبلغ (تومان)"
          inputMode="numeric"
          dir="ltr"
          placeholder={ZERO_PLACEHOLDER}
          value={principal}
          onChange={(event) => {
            const latin = toLatinDigits(event.target.value).replace(/[^\d]/g, '')
            setValue('principal', latin, { shouldValidate: false })
          }}
          hint={
            numericPrincipal > 0
              ? `معادل: ${formatDigits(numericPrincipal)} تومان`
              : undefined
          }
          error={errors.principal?.message}
        />

        <div className="grid gap-4 sm:grid-cols-2">
          <JalaliDatePicker
            label={direction === 'payable' ? 'تاریخ ایجاد بدهی' : 'تاریخ ایجاد طلب'}
            value={issuedOn}
            onChange={(iso) => setValue('issued_on', iso, { shouldValidate: true })}
            error={errors.issued_on?.message}
            disableFuture
          />

          <JalaliDatePicker
            label="تاریخ سررسید"
            value={dueOn}
            onChange={(iso) => setValue('due_on', iso, { shouldValidate: true })}
            error={errors.due_on?.message || (dueBeforeIssued ? 'تاریخ سررسید قبل از تاریخ ایجاد است.' : undefined)}
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="debt-description" className="text-[13px] font-medium text-ink-soft">
            توضیحات <span className="font-normal text-ink-faint">(اختیاری)</span>
          </label>
          <textarea
            id="debt-description"
            rows={3}
            placeholder={`مثلاً وام خرید خودرو، ${formatDigits(24)} قسط ماهانه`}
            className="w-full resize-none rounded-control border border-border-strong bg-surface p-3 text-sm text-ink placeholder:text-ink-faint focus:border-brand-500"
            {...register('description')}
          />
          {errors.description?.message ? (
            <p role="alert" className="text-xs text-critical-600">
              {errors.description.message}
            </p>
          ) : null}
        </div>

        {formError ? (
          <p role="alert" className="rounded-control bg-critical-50 px-3 py-2 text-xs text-critical-700">
            {formError}
          </p>
        ) : null}
      </form>
    </ResponsiveDialog>
  )
}
