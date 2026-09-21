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
import { JalaliDatePicker } from '../../components/ui/JalaliDatePicker'
import { CategoryIcon } from '../../components/common/CategoryIcon'
import { SpendingTypeSelector } from '../../components/common/SpendingTypeSelector'
import {
  useAccounts,
  useCategoryPicker,
  useCreateTransaction,
  useUpdateTransaction,
} from '../../hooks/queries'
import { errorMessage, fieldErrors } from '../../services/client'
import { ZERO_PLACEHOLDER, formatDigits, normalizeNumericInput, toLatinDigits } from '../../utils/format'
import { currentJalaliMonth, jalaliToIso } from '../../utils/jalali'
import type { CategoryKind, SpendingType, Transaction } from '../../types'

// ---------------------------------------------------------------------------
// Validation
//
// The amount arrives from a Persian-formatted field, so it is normalised to
// Latin digits before the numeric check. Zod then enforces the same rules the
// server does, so the user gets the error instantly rather than on submit.
// ---------------------------------------------------------------------------

const formSchema = z.object({
  transaction_type: z.enum(['expense', 'income']),
  amount: z
    .string()
    .min(1, 'مبلغ را وارد کنید.')
    .refine((value) => Number(normalizeNumericInput(value)) > 0, {
      message: 'مبلغ باید بیشتر از صفر باشد.',
    }),
  category: z.string().min(1, 'دسته‌بندی را انتخاب کنید.'),
  account: z.string().optional(),
  // Always present in the form state; stripped from the payload for income,
  // where the server rejects it.
  spending_type: z.enum(['essential', 'flexible', 'wasted']),
  occurred_on: z.string().min(1, 'تاریخ را انتخاب کنید.'),
  description: z.string().max(255, 'توضیح بیش از حد طولانی است.').optional(),
})

type FormValues = z.infer<typeof formSchema>

function todayIso(): string {
  const { year, month } = currentJalaliMonth()
  return jalaliToIso(year, month, new Date().getDate())
}

export interface TransactionFormProps {
  open: boolean
  /** `null` means "create"; a transaction means "edit". */
  transaction: Transaction | null
  onClose: () => void
  onDelete?: (id: number) => void
  isDeleting?: boolean
}

/**
 * The full create/edit form, reached by tapping a row in the ledger.
 *
 * The quick-entry sheet exists for speed; this exists for completeness —
 * account, note, and deletion all live here.
 */
export function TransactionForm({
  open,
  transaction,
  onClose,
  onDelete,
  isDeleting = false,
}: TransactionFormProps) {
  const isEditing = transaction !== null
  const [formError, setFormError] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const { showToast } = useToast()

  const createTransaction = useCreateTransaction()
  const updateTransaction = useUpdateTransaction()

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    reset,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      transaction_type: 'expense',
      amount: '',
      category: '',
      account: '',
      spending_type: 'flexible' as SpendingType,
      occurred_on: todayIso(),
      description: '',
    },
  })

  const kind = watch('transaction_type')
  const categoryId = watch('category')
  const amount = watch('amount')
  const occurredOn = watch('occurred_on')
  const spendingType = watch('spending_type')

  const { data: categories } = useCategoryPicker(kind as CategoryKind)
  const { data: accounts } = useAccounts()

  // Load the row being edited into the form whenever it changes.
  useEffect(() => {
    if (!open) return
    setFormError(null)
    setConfirmDelete(false)

    if (transaction) {
      reset({
        transaction_type: transaction.transaction_type,
        amount: String(Math.round(Number(transaction.amount))),
        category: String(transaction.category),
        account: transaction.account ? String(transaction.account) : '',
        // Older rows recorded before the classification existed fall back to
        // flexible rather than showing an empty picker.
        spending_type: (transaction.spending_type ?? 'flexible') as SpendingType,
        occurred_on: transaction.occurred_on,
        description: transaction.description || '',
      })
    } else {
      reset({
        transaction_type: 'expense',
        amount: '',
        category: '',
        account: '',
        spending_type: 'flexible' as SpendingType,
        occurred_on: todayIso(),
        description: '',
      })
    }
  }, [open, transaction, reset])

  const numericAmount = Number(normalizeNumericInput(amount)) || 0

  const submit = handleSubmit(async (values) => {
    setFormError(null)

    const payload = {
      transaction_type: values.transaction_type,
      amount: String(Number(normalizeNumericInput(values.amount))),
      category: Number(values.category),
      account: values.account ? Number(values.account) : null,
      // Income never carries a classification — the server rejects the field.
      ...(values.transaction_type === 'expense'
        ? { spending_type: values.spending_type }
        : {}),
      occurred_on: values.occurred_on,
      description: values.description?.trim() ?? '',
    }

    try {
      if (isEditing && transaction) {
        await updateTransaction.mutateAsync({ id: transaction.id, ...payload })
        showToast({ message: 'تغییرات تراکنش ذخیره شد.' })
      } else {
        await createTransaction.mutateAsync(payload)
        showToast({
          message:
            values.transaction_type === 'income' ? 'درآمد ثبت شد.' : 'هزینه ثبت شد.',
        })
      }
      onClose()
    } catch (error) {
      const fields = fieldErrors(error)
      let matched = false
      for (const [field, message] of Object.entries(fields)) {
        if (
          field === 'amount' ||
          field === 'category' ||
          field === 'account' ||
          field === 'occurred_on' ||
          field === 'description'
        ) {
          setError(field as keyof FormValues, { message })
          matched = true
        }
      }
      setFormError(
        matched ? null : errorMessage(error, 'ذخیره تغییرات انجام نشد. دوباره تلاش کنید.'),
      )
    }
  })

  return (
    <ResponsiveDialog
      open={open}
      onClose={onClose}
      title={isEditing ? 'ویرایش تراکنش' : 'ثبت تراکنش'}
      footer={
        <div className="flex items-center gap-2">
          {isEditing && onDelete ? (
            confirmDelete ? (
              <>
                <Button
                  variant="danger"
                  onClick={() => {
                    if (transaction) onDelete(transaction.id)
                    onClose()
                  }}
                  isLoading={isDeleting}
                  className="flex-1"
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
                onClick={() => setConfirmDelete(true)}
                className="text-critical-600"
                leadingIcon={<Trash2 className="size-4" aria-hidden="true" />}
              >
                حذف
              </Button>
            )
          ) : (
            <Button variant="ghost" onClick={onClose}>
              انصراف
            </Button>
          )}

          {!confirmDelete ? (
            <Button onClick={submit} isLoading={isSubmitting} className="flex-1">
              {isEditing ? 'ذخیره تغییرات' : 'ثبت تراکنش'}
            </Button>
          ) : null}
        </div>
      }
    >
      <form onSubmit={submit} noValidate className="space-y-4">
        <fieldset>
          <legend className="mb-2 text-[13px] font-medium text-ink-soft">نوع تراکنش</legend>
          <div className="grid grid-cols-2 gap-2">
            {(['expense', 'income'] as const).map((option) => (
              <label
                key={option}
                className={[
                  'flex h-11 cursor-pointer items-center justify-center gap-2 rounded-control border text-[13px] font-medium transition-colors',
                  kind === option
                    ? option === 'expense'
                      ? 'border-critical-500 bg-critical-50 text-critical-700'
                      : 'border-positive-500 bg-positive-50 text-positive-700'
                    : 'border-border-strong bg-surface text-ink-soft hover:bg-surface-muted',
                ].join(' ')}
              >
                <input
                  type="radio"
                  value={option}
                  className="sr-only"
                  {...register('transaction_type', {
                    onChange: () => setValue('category', ''),
                  })}
                />
                {option === 'expense' ? 'هزینه' : 'درآمد'}
              </label>
            ))}
          </div>
        </fieldset>

        <Input
          label="مبلغ (تومان)"
          inputMode="numeric"
          dir="ltr"
          placeholder={ZERO_PLACEHOLDER}
          value={amount}
          onChange={(event) => {
            const latin = toLatinDigits(event.target.value).replace(/[^\d]/g, '')
            setValue('amount', latin, { shouldValidate: false })
          }}
          hint={numericAmount > 0 ? `معادل: ${formatDigits(numericAmount)} تومان` : undefined}
          error={errors.amount?.message}
        />

        <div className="flex flex-col gap-1.5">
          <span className="text-[13px] font-medium text-ink-soft">دسته‌بندی</span>
          {!categories || categories.length === 0 ? (
            <p className="text-xs text-ink-faint">در حال بارگذاری…</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {categories.map((category) => {
                const active = String(category.id) === categoryId
                return (
                  <button
                    key={category.id}
                    type="button"
                    onClick={() => setValue('category', String(category.id), { shouldValidate: true })}
                    aria-pressed={active}
                    className={[
                      'flex items-center gap-2 rounded-pill border px-3 py-2 text-[12.5px] transition-colors',
                      active
                        ? 'border-brand-500 bg-brand-50 font-medium text-brand-700'
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
          {errors.category?.message ? (
            <p role="alert" className="text-xs text-critical-600">
              {errors.category.message}
            </p>
          ) : null}
        </div>

        {/* Spending classification — expenses only */}
        {kind === 'expense' ? (
          <div className="flex flex-col gap-1.5">
            <span className="text-[13px] font-medium text-ink-soft">نوع هزینه</span>
            <SpendingTypeSelector
              name="spending-type"
              value={spendingType}
              onChange={(value) => setValue('spending_type', value)}
            />
          </div>
        ) : null}

        <div className="grid gap-4 sm:grid-cols-2">
          <JalaliDatePicker
            label="تاریخ"
            value={occurredOn}
            onChange={(iso) => setValue('occurred_on', iso, { shouldValidate: true })}
            error={errors.occurred_on?.message}
            disableFuture
          />

          <Select
            label="حساب"
            placeholder="بدون حساب"
            options={(accounts?.results ?? []).map((account) => ({
              value: String(account.id),
              label: account.name,
            }))}
            {...register('account')}
          />
        </div>

        <Input
          label="توضیح"
          placeholder="مثلاً خرید هفتگی"
          error={errors.description?.message}
          {...register('description')}
        />

        {formError ? (
          <p role="alert" className="rounded-control bg-critical-50 px-3 py-2 text-xs text-critical-700">
            {formError}
          </p>
        ) : null}
      </form>
    </ResponsiveDialog>
  )
}
