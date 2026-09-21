import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Trash2 } from 'lucide-react'
import { ResponsiveDialog } from '../../components/ui/ResponsiveDialog'
import { Button } from '../../components/ui/Button'
import { useToast } from '../../components/ui/Toast'
import { Input } from '../../components/ui/Input'
import { Select } from '../../components/ui/Select'
import { useCreateAccount, useDeleteAccount, useUpdateAccount } from '../../hooks/queries'
import { errorMessage, fieldErrors } from '../../services/client'
import { ZERO_PLACEHOLDER, formatDigits, normalizeNumericInput, toLatinDigits } from '../../utils/format'
import type { Account, AccountType } from '../../types'

const ACCOUNT_TYPES: Array<{ value: AccountType; label: string }> = [
  { value: 'bank', label: 'حساب بانکی' },
  { value: 'cash', label: 'کیف پول نقدی' },
  { value: 'card', label: 'کارت بانکی' },
  { value: 'investment', label: 'حساب سرمایه‌گذاری' },
  { value: 'savings', label: 'سپرده' },
  { value: 'credit', label: 'کارت اعتباری' },
  { value: 'other', label: 'سایر' },
]

// The palette is fixed rather than a free colour input: a small, curated set
// keeps the account list visually coherent.
const COLOURS = ['#3566e8', '#12a150', '#e08c00', '#dc2b2b', '#5b5bd6', '#0ea5b7', '#8b5cf6']

const schema = z.object({
  name: z.string().min(1, 'نام حساب را وارد کنید.').max(120, 'نام بیش از حد طولانی است.'),
  account_type: z.string().min(1, 'نوع حساب را انتخاب کنید.'),
  institution: z.string().max(120, 'نام بیش از حد طولانی است.').optional(),
  opening_balance: z.string().optional(),
  color: z.string(),
})

type FormValues = z.infer<typeof schema>

export interface AccountFormProps {
  open: boolean
  account: Account | null
  onClose: () => void
}

/**
 * Create or edit a wallet/account.
 *
 * The opening balance is only meaningful at creation — once transactions
 * exist, the current balance is derived from them and editing the opening
 * figure would silently shift history.
 */
export function AccountForm({ open, account, onClose }: AccountFormProps) {
  const isEditing = account !== null
  const [formError, setFormError] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const createAccount = useCreateAccount()
  const updateAccount = useUpdateAccount()
  const deleteAccount = useDeleteAccount()
  const { showToast } = useToast()

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
      name: '',
      account_type: 'bank',
      institution: '',
      opening_balance: '',
      color: COLOURS[0],
    },
  })

  const openingBalance = watch('opening_balance') ?? ''
  const colour = watch('color')

  useEffect(() => {
    if (!open) return
    setFormError(null)
    setConfirmDelete(false)

    if (account) {
      reset({
        name: account.name,
        account_type: account.account_type,
        institution: account.institution || '',
        opening_balance: String(Math.round(Number(account.opening_balance))),
        color: account.color || COLOURS[0],
      })
    } else {
      reset({
        name: '',
        account_type: 'bank',
        institution: '',
        opening_balance: '',
        color: COLOURS[0],
      })
    }
  }, [open, account, reset])

  const submit = handleSubmit(async (values) => {
    setFormError(null)

    const payload: Record<string, unknown> = {
      name: values.name.trim(),
      account_type: values.account_type,
      institution: values.institution?.trim() || '',
      color: values.color,
    }

    // Only send the opening balance when creating — see the note above.
    if (!isEditing) {
      payload.opening_balance = String(
        Number(normalizeNumericInput(values.opening_balance ?? '')) || 0,
      )
    }

    try {
      if (isEditing && account) {
        await updateAccount.mutateAsync({ id: account.id, ...payload })
        showToast({ message: 'تغییرات حساب ذخیره شد.' })
      } else {
        await createAccount.mutateAsync(payload)
        showToast({ message: 'حساب جدید اضافه شد.' })
      }
      onClose()
    } catch (error) {
      const fields = fieldErrors(error)
      let matched = false
      for (const [field, message] of Object.entries(fields)) {
        if (field === 'name' || field === 'account_type' || field === 'opening_balance') {
          setError(field as keyof FormValues, { message })
          matched = true
        }
      }
      setFormError(matched ? null : errorMessage(error, 'ذخیره حساب انجام نشد. دوباره تلاش کنید.'))
    }
  })

  return (
    <ResponsiveDialog
      open={open}
      onClose={onClose}
      title={isEditing ? 'ویرایش حساب' : 'افزودن حساب'}
      footer={
        <div className="flex items-center gap-2">
          {isEditing ? (
            confirmDelete ? (
              <>
                <Button
                  variant="danger"
                  className="flex-1"
                  isLoading={deleteAccount.isPending}
                  onClick={() => {
                    if (account)
                      deleteAccount.mutate(account.id, {
                        onSuccess: () => showToast({ message: 'حساب حذف شد.' }),
                      })
                    onClose()
                  }}
                >
                  حذف قطعی
                </Button>
                <Button variant="ghost" onClick={() => setConfirmDelete(false)}>
                  انصراف
                </Button>
              </>
            ) : (
              <Button
                variant="ghost"
                className="text-critical-600"
                onClick={() => setConfirmDelete(true)}
                leadingIcon={<Trash2 className="size-4" aria-hidden="true" />}
              >
                حذف
              </Button>
            )
          ) : null}

          {!confirmDelete ? (
            <Button onClick={submit} isLoading={isSubmitting} className="flex-1">
              {isEditing ? 'ذخیره تغییرات' : 'افزودن حساب'}
            </Button>
          ) : null}
        </div>
      }
    >
      <form onSubmit={submit} noValidate className="space-y-4">
        <Input
          label="نام حساب"
          placeholder="مثلاً بانک ملت"
          error={errors.name?.message}
          {...register('name')}
        />

        <Select
          label="نوع حساب"
          options={ACCOUNT_TYPES}
          error={errors.account_type?.message}
          {...register('account_type')}
        />

        <Input
          label="نهاد / بانک"
          placeholder="مثلاً بانک ملت"
          hint="اختیاری — فقط برای نمایش"
          error={errors.institution?.message}
          {...register('institution')}
        />

        {!isEditing ? (
          <div className="flex flex-col gap-1.5">
            <label htmlFor="account-opening-balance" className="text-[13px] font-medium text-ink-soft">
              موجودی اولیه (تومان)
            </label>
            <div className="relative">
              <input
                id="account-opening-balance"
                inputMode="numeric"
                dir="ltr"
                placeholder={ZERO_PLACEHOLDER}
                value={openingBalance ? formatDigits(Number(openingBalance)) : ''}
                onChange={(event) =>
                  setValue('opening_balance', toLatinDigits(event.target.value).replace(/[^\d]/g, ''))
                }
                className="h-11 w-full rounded-control border border-border-strong bg-surface px-3 pe-14 text-sm text-ink ltr-nums placeholder:text-ink-faint focus:border-brand-500"
              />
              <span className="pointer-events-none absolute inset-y-0 end-3 flex items-center text-[11px] text-ink-faint">
                تومان
              </span>
            </div>
            <p className="text-xs text-ink-faint">
              پس از ثبت، موجودی این حساب از روی تراکنش‌ها محاسبه می‌شود.
            </p>
          </div>
        ) : (
          <p className="rounded-control bg-surface-muted px-3 py-2 text-[11.5px] leading-5 text-ink-faint">
            {'موجودی فعلی این حساب: '}
            <span className="ltr-nums font-medium text-ink-soft">
              {account?.current_balance_display}
            </span>
            {' — این مقدار از تراکنش‌های ثبت‌شده محاسبه شده است.'}
          </p>
        )}

        <fieldset>
          <legend className="mb-2 text-[13px] font-medium text-ink-soft">رنگ</legend>
          <div className="flex flex-wrap gap-2">
            {COLOURS.map((option) => (
              <label
                key={option}
                className={[
                  'flex size-10 cursor-pointer items-center justify-center rounded-control border-2 transition-colors',
                  colour === option ? 'border-ink' : 'border-transparent',
                ].join(' ')}
              >
                <input
                  type="radio"
                  value={option}
                  className="sr-only"
                  {...register('color')}
                />
                <span
                  className="size-6 rounded-pill"
                  style={{ backgroundColor: option }}
                  aria-label={`رنگ ${option}`}
                />
              </label>
            ))}
          </div>
        </fieldset>

        {formError ? (
          <p role="alert" className="rounded-control bg-critical-50 px-3 py-2 text-xs text-critical-700">
            {formError}
          </p>
        ) : null}
      </form>
    </ResponsiveDialog>
  )
}
