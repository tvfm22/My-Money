import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { ResponsiveDialog } from '../../components/ui/ResponsiveDialog'
import { Button } from '../../components/ui/Button'
import { useToast } from '../../components/ui/Toast'
import { Input } from '../../components/ui/Input'
import { Select } from '../../components/ui/Select'
import { JalaliDatePicker } from '../../components/ui/JalaliDatePicker'
import { useAccounts, useCreateAsset, useUpdateAsset } from '../../hooks/queries'
import { errorMessage, fieldErrors } from '../../services/client'
import { ZERO_PLACEHOLDER, formatDigits, formatPercentChange, normalizeNumericInput, toLatinDigits } from '../../utils/format'
import type { Asset, AssetType } from '../../types'

/**
 * The asset types the server accepts.
 *
 * Kept in the same order as the model's choices so the dropdown reads the way
 * the domain thinks about it: liquid first, then investments, then property.
 */
const ASSET_TYPES: Array<{ value: AssetType; label: string }> = [
  { value: 'bank_account', label: 'حساب بانکی' },
  { value: 'cash', label: 'وجه نقد' },
  { value: 'deposit', label: 'سپرده' },
  { value: 'gold_fund', label: 'صندوق طلا' },
  { value: 'gold', label: 'طلا' },
  { value: 'currency', label: 'ارز' },
  { value: 'stocks', label: 'سهام' },
  { value: 'crypto', label: 'رمزارز' },
  { value: 'real_estate', label: 'ملک' },
  { value: 'vehicle', label: 'خودرو' },
  { value: 'other', label: 'سایر' },
]

/** Types where tracking units and a unit price is meaningful. */
const QUANTITY_TYPES: AssetType[] = ['gold_fund', 'gold', 'stocks', 'currency', 'crypto']

const schema = z.object({
  name: z.string().min(1, 'نام دارایی را وارد کنید.').max(150, 'نام بیش از حد طولانی است.'),
  asset_type: z.string().min(1, 'نوع دارایی را انتخاب کنید.'),
  current_value: z
    .string()
    .min(1, 'ارزش فعلی را وارد کنید.')
    .refine((value) => Number(normalizeNumericInput(value)) >= 0, {
      message: 'ارزش فعلی نمی‌تواند منفی باشد.',
    }),
  purchase_value: z.string().optional(),
  purchase_date: z.string().optional(),
  quantity: z.string().optional(),
  unit: z.string().max(30, 'واحد بیش از حد طولانی است.').optional(),
  provider: z.string().max(120, 'نام بیش از حد طولانی است.').optional(),
  account: z.string().optional(),
  description: z.string().max(500, 'توضیحات بیش از حد طولانی است.').optional(),
})

type FormValues = z.infer<typeof schema>

export interface AssetFormProps {
  open: boolean
  asset: Asset | null
  onClose: () => void
}

/** Create or edit a holding. Valuations are added separately, from the list. */
export function AssetForm({ open, asset, onClose }: AssetFormProps) {
  const isEditing = asset !== null
  const [formError, setFormError] = useState<string | null>(null)
  const { showToast } = useToast()

  const createAsset = useCreateAsset()
  const updateAsset = useUpdateAsset()
  const { data: accounts } = useAccounts()

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
      asset_type: 'bank_account',
      current_value: '',
      purchase_value: '',
      purchase_date: '',
      quantity: '',
      unit: '',
      provider: '',
      account: '',
      description: '',
    },
  })

  const assetType = watch('asset_type') as AssetType
  const currentValue = watch('current_value')
  const purchaseValue = watch('purchase_value')
  const purchaseDate = watch('purchase_date') ?? ''
  const quantity = watch('quantity')

  const showQuantity = QUANTITY_TYPES.includes(assetType)

  useEffect(() => {
    if (!open) return
    setFormError(null)

    if (asset) {
      reset({
        name: asset.name,
        asset_type: asset.asset_type,
        current_value: String(Math.round(Number(asset.current_value))),
        purchase_value: String(Math.round(Number(asset.purchase_value))) || '',
        purchase_date: asset.purchase_date ?? '',
        quantity: asset.quantity ? String(Number(asset.quantity)) : '',
        unit: asset.unit || '',
        provider: asset.provider || '',
        account: asset.account ? String(asset.account) : '',
        description: asset.description || '',
      })
    } else {
      reset({
        name: '',
        asset_type: 'bank_account',
        current_value: '',
        purchase_value: '',
        purchase_date: '',
        quantity: '',
        unit: '',
        provider: '',
        account: '',
        description: '',
      })
    }
  }, [open, asset, reset])

  const numericCurrent = Number(normalizeNumericInput(currentValue)) || 0
  const numericPurchase = Number(normalizeNumericInput(purchaseValue ?? '')) || 0
  const nominalReturn = numericCurrent - numericPurchase
  const returnPercent = numericPurchase > 0 ? (nominalReturn / numericPurchase) * 100 : null
  const numericQuantity = Number(normalizeNumericInput(quantity ?? '')) || 0

  const submit = handleSubmit(async (values) => {
    setFormError(null)

    // The server stores a unit price alongside the quantity so a holding can
    // be re-valued by price alone later.
    const unitPrice =
      showQuantity && numericQuantity > 0
        ? String(numericCurrent / numericQuantity)
        : null

    const payload: Record<string, unknown> = {
      name: values.name.trim(),
      asset_type: values.asset_type,
      current_value: String(numericCurrent),
      purchase_value: values.purchase_value
        ? String(Number(normalizeNumericInput(values.purchase_value)))
        : '0',
      purchase_date: values.purchase_date || null,
      quantity: showQuantity && values.quantity ? String(Number(normalizeNumericInput(values.quantity))) : null,
      unit: showQuantity ? values.unit?.trim() || '' : '',
      unit_price: unitPrice,
      provider: values.provider?.trim() || '',
      account: values.account ? Number(values.account) : null,
      description: values.description?.trim() || '',
    }

    try {
      if (isEditing && asset) {
        await updateAsset.mutateAsync({ id: asset.id, ...payload })
        showToast({ message: 'تغییرات دارایی ذخیره شد.' })
      } else {
        await createAsset.mutateAsync(payload)
        showToast({ message: 'دارایی جدید اضافه شد.' })
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
      setFormError(
        matched ? null : errorMessage(error, 'ذخیره دارایی انجام نشد. دوباره تلاش کنید.'),
      )
    }
  })

  return (
    <ResponsiveDialog
      open={open}
      onClose={onClose}
      title={isEditing ? 'ویرایش دارایی' : 'افزودن دارایی'}
      footer={
        <div className="flex gap-2">
          <Button variant="ghost" onClick={onClose} className="flex-1">
            انصراف
          </Button>
          <Button onClick={submit} isLoading={isSubmitting} className="flex-[2]">
            {isEditing ? 'ذخیره تغییرات' : 'افزودن'}
          </Button>
        </div>
      }
    >
      <form onSubmit={submit} noValidate className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Input
            label="نام دارایی"
            placeholder="مثلاً صندوق طلای مفید"
            error={errors.name?.message}
            {...register('name')}
          />

          <Select
            label="نوع"
            options={ASSET_TYPES}
            error={errors.asset_type?.message}
            {...register('asset_type')}
          />
        </div>

        <MoneyInput
          id="asset-current-value"
          label="ارزش فعلی (تومان)"
          value={currentValue}
          onChange={(value) => setValue('current_value', value, { shouldValidate: false })}
          error={errors.current_value?.message}
        />

        {/* Units — only for holdings measured in units. */}
        {showQuantity ? (
          <div className="grid gap-4 sm:grid-cols-2">
            <Input
              label="تعداد / مقدار"
              inputMode="decimal"
              dir="ltr"
              placeholder={`مثلاً ${formatDigits(125)}`}
              value={quantity ?? ''}
              onChange={(event) => {
                const latin = toLatinDigits(event.target.value).replace(/[^\d.]/g, '')
                setValue('quantity', latin, { shouldValidate: false })
              }}
              error={errors.quantity?.message}
            />

            <Input
              label="واحد"
              placeholder="مثلاً واحد، گرم، سهم"
              error={errors.unit?.message}
              {...register('unit')}
            />
          </div>
        ) : null}

        {showQuantity && numericQuantity > 0 && numericCurrent > 0 ? (
          <p className="rounded-control bg-surface-muted px-3 py-2 text-[11.5px] text-ink-soft">
            {'ارزش هر واحد: '}
            <span className="ltr-nums font-medium text-ink">
              {formatDigits(Math.round(numericCurrent / numericQuantity))}
              {' تومان'}
            </span>
          </p>
        ) : null}

        <div className="grid gap-4 sm:grid-cols-2">
          <MoneyInput
            id="asset-purchase-value"
            label="ارزش خرید (اختیاری)"
            value={purchaseValue ?? ''}
            onChange={(value) => setValue('purchase_value', value, { shouldValidate: false })}
            error={errors.purchase_value?.message}
          />

          <JalaliDatePicker
            label="تاریخ خرید (اختیاری)"
            value={purchaseDate}
            onChange={(iso) => setValue('purchase_date', iso)}
            error={errors.purchase_date?.message}
            disableFuture
          />
        </div>

        {/* Live nominal return preview, so the effect of the two numbers is
            visible before saving. */}
        {numericPurchase > 0 ? (
          <div
            className={[
              'flex items-center justify-between gap-3 rounded-control px-3 py-2.5',
              nominalReturn >= 0 ? 'bg-positive-50' : 'bg-critical-50',
            ].join(' ')}
          >
            <span
              className={[
                'text-[12px]',
                nominalReturn >= 0 ? 'text-positive-700' : 'text-critical-700',
              ].join(' ')}
            >
              بازده اسمی
            </span>
            <span className="flex items-center gap-2">
              <span
                className={[
                  'ltr-nums text-[13px] font-semibold',
                  nominalReturn >= 0 ? 'text-positive-700' : 'text-critical-700',
                ].join(' ')}
              >
                {`${nominalReturn >= 0 ? '+' : '−'}${formatDigits(Math.abs(Math.round(nominalReturn)))}`}
              </span>
              {returnPercent !== null ? (
                <span
                  className={[
                    'ltr-nums rounded-pill px-2 py-0.5 text-[10.5px] font-medium',
                    nominalReturn >= 0
                      ? 'bg-positive-100 text-positive-700'
                      : 'bg-critical-100 text-critical-700',
                  ].join(' ')}
                >
                  {formatPercentChange(returnPercent, 1)}
                </span>
              ) : null}
            </span>
          </div>
        ) : null}

        <div className="grid gap-4 sm:grid-cols-2">
          <Input
            label="نهاد / ارائه‌دهنده (اختیاری)"
            placeholder="مثلاً بانک ملت"
            error={errors.provider?.message}
            {...register('provider')}
          />

          <Select
            label="حساب مرتبط (اختیاری)"
            placeholder="بدون حساب"
            options={(accounts?.results ?? []).map((account) => ({
              value: String(account.id),
              label: account.name,
            }))}
            {...register('account')}
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="asset-description" className="text-[13px] font-medium text-ink-soft">
            توضیحات <span className="font-normal text-ink-faint">(اختیاری)</span>
          </label>
          <textarea
            id="asset-description"
            rows={2}
            placeholder="هر توضیحی که لازم می‌دانید"
            className="w-full resize-none rounded-control border border-border-strong bg-surface p-3 text-sm text-ink placeholder:text-ink-faint focus:border-brand-500"
            {...register('description')}
          />
        </div>

        <p className="rounded-control bg-info-50 px-3 py-2 text-[11px] leading-5 text-info-600">
          قیمت‌های بازار به‌صورت خودکار دریافت نمی‌شوند. ارزش دارایی را دستی به‌روزرسانی کنید تا
          محاسبات دقیق بماند.
        </p>

        {formError ? (
          <p role="alert" className="rounded-control bg-critical-50 px-3 py-2 text-xs text-critical-700">
            {formError}
          </p>
        ) : null}
      </form>
    </ResponsiveDialog>
  )
}

function MoneyInput({
  label,
  value,
  onChange,
  error,
  id,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  error?: string
  id: string
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-[13px] font-medium text-ink-soft">
        {label}
      </label>
      <div className="relative">
        <input
          id={id}
          inputMode="numeric"
          dir="ltr"
          placeholder={ZERO_PLACEHOLDER}
          value={value ? formatDigits(Number(value)) : ''}
          onChange={(event) => {
            const latin = toLatinDigits(event.target.value).replace(/[^\d]/g, '')
            onChange(latin)
          }}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : undefined}
          className={[
            'h-11 w-full rounded-control border bg-surface px-3 pe-14 text-sm text-ink ltr-nums',
            'placeholder:text-ink-faint',
            error ? 'border-critical-500' : 'border-border-strong focus:border-brand-500',
          ].join(' ')}
        />
        <span className="pointer-events-none absolute inset-y-0 end-3 flex items-center text-[11px] text-ink-faint">
          تومان
        </span>
      </div>
      {error ? (
        <p id={`${id}-error`} role="alert" className="text-xs text-critical-600">
          {error}
        </p>
      ) : null}
    </div>
  )
}
