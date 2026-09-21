import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { ArrowRight, Calendar, Plus, Trash2, Wallet } from 'lucide-react'
import { Card } from '../../components/ui/Card'
import { Button } from '../../components/ui/Button'
import { useToast } from '../../components/ui/Toast'
import { Input } from '../../components/ui/Input'
import { Badge } from '../../components/ui/Badge'
import { EmptyState } from '../../components/ui/EmptyState'
import { ErrorState } from '../../components/ui/ErrorState'
import { LoadingCard } from '../../components/ui/LoadingState'
import { ResponsiveDialog } from '../../components/ui/ResponsiveDialog'
import { JalaliDatePicker } from '../../components/ui/JalaliDatePicker'
import { MoneyDisplay } from '../../components/common/MoneyDisplay'
import { DebtForm } from './DebtForm'
import {
  useAddDebtPayment,
  useDebt,
  useDeleteDebtPayment,
  useDeleteDebt,
} from '../../hooks/queries'
import { errorMessage, fieldErrors } from '../../services/client'
import { formatDigits, formatPercent, normalizeNumericInput, toLatinDigits } from '../../utils/format'
import { currentJalaliMonth, formatRelativeDay, jalaliToIso } from '../../utils/jalali'
import type { DebtStatusValue } from '../../types'

const STATUS_VARIANT: Record<DebtStatusValue, 'positive' | 'info' | 'caution' | 'critical'> = {
  active: 'info',
  partial: 'caution',
  settled: 'positive',
  overdue: 'critical',
}

const paymentSchema = z.object({
  amount: z
    .string()
    .min(1, 'مبلغ را وارد کنید.')
    .refine((value) => Number(normalizeNumericInput(value)) > 0, {
      message: 'مبلغ باید بیشتر از صفر باشد.',
    }),
  paid_on: z.string().min(1, 'تاریخ را انتخاب کنید.'),
  note: z.string().max(255, 'توضیح بیش از حد طولانی است.').optional(),
})

type PaymentValues = z.infer<typeof paymentSchema>

export function DebtDetailPage() {
  const { id } = useParams<{ id: string }>()
  const debtId = Number(id)
  const navigate = useNavigate()

  const [isPaymentOpen, setIsPaymentOpen] = useState(false)
  const [isEditOpen, setIsEditOpen] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const { data: debt, isPending, isError, error, refetch, isFetching } = useDebt(debtId)
  const addPayment = useAddDebtPayment()
  const removePayment = useDeleteDebtPayment()
  const deleteDebt = useDeleteDebt()
  const { showToast } = useToast()

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    reset,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<PaymentValues>({
    resolver: zodResolver(paymentSchema),
    defaultValues: { amount: '', paid_on: '', note: '' },
  })

  const paymentAmount = watch('amount')
  const paidOn = watch('paid_on')

  const openPayment = () => {
    if (!debt) return
    const { year, month } = currentJalaliMonth()
    reset({
      // Pre-fill with the outstanding balance — the common case by far.
      amount: String(Math.round(Number(debt.remaining_amount))),
      paid_on: jalaliToIso(year, month, new Date().getDate()),
      note: '',
    })
    setActionError(null)
    setIsPaymentOpen(true)
  }

  const submitPayment = handleSubmit(async (values) => {
    setActionError(null)
    try {
      await addPayment.mutateAsync({
        debtId,
        amount: String(Number(normalizeNumericInput(values.amount))),
        paid_on: values.paid_on,
        note: values.note?.trim() ?? '',
      })
      showToast({ message: 'پرداخت ثبت شد.' })
      setIsPaymentOpen(false)
    } catch (err) {
      const fields = fieldErrors(err)
      let matched = false
      for (const [field, message] of Object.entries(fields)) {
        if (field === 'amount' || field === 'paid_on' || field === 'note') {
          setError(field as keyof PaymentValues, { message })
          matched = true
        }
      }
      setActionError(
        matched ? null : errorMessage(err, 'ثبت پرداخت انجام نشد. دوباره تلاش کنید.'),
      )
    }
  })

  if (isError) {
    return (
      <ErrorState
        message={errorMessage(error, 'اطلاعات این مورد دریافت نشد.')}
        onRetry={() => void refetch()}
        isRetrying={isFetching}
      />
    )
  }

  if (isPending || !debt) {
    return (
      <div className="space-y-4">
        <LoadingCard />
        <LoadingCard />
      </div>
    )
  }

  const paidPercent = Number(debt.paid_percent || 0)
  const remaining = Number(debt.remaining_amount || 0)

  return (
    <>
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Link
            to="/debts"
            aria-label="بازگشت"
            className="flex size-9 items-center justify-center rounded-control text-ink-soft transition-colors hover:bg-surface-muted"
          >
            <ArrowRight className="size-4" aria-hidden="true" />
          </Link>
          <div className="min-w-0">
            <h1 className="truncate text-lg font-bold text-ink">{debt.counterparty}</h1>
            <p className="mt-0.5 text-[12px] text-ink-soft">
              {debt.direction === 'payable' ? 'بدهی من' : 'طلب من'}
            </p>
          </div>
        </div>

        <Badge variant={STATUS_VARIANT[debt.status]}>{debt.status_label}</Badge>
      </div>

      {/* Headline figures */}
      <Card className="mb-4">
        <div className="grid grid-cols-3 gap-3">
          <div>
            <p className="text-[11.5px] text-ink-faint">مبلغ کل</p>
            <p className="mt-1 text-[14px] font-semibold text-ink">
              <MoneyDisplay value={debt.principal} />
            </p>
          </div>
          <div className="border-x border-border px-3">
            <p className="text-[11.5px] text-ink-faint">
              {debt.direction === 'payable' ? 'پرداخت‌شده' : 'دریافت‌شده'}
            </p>
            <p className="mt-1 text-[14px] font-semibold text-positive-600">
              <MoneyDisplay value={debt.paid_amount} />
            </p>
          </div>
          <div>
            <p className="text-[11.5px] text-ink-faint">باقی‌مانده</p>
            <p className="mt-1 text-[14px] font-semibold text-ink">
              <MoneyDisplay value={debt.remaining_amount} />
            </p>
          </div>
        </div>

        <div className="mt-4">
          <div className="mb-1.5 flex items-center justify-between text-[11.5px] text-ink-faint">
            <span>پیشرفت تسویه</span>
            <span className="ltr-nums">{formatPercent(paidPercent)}</span>
          </div>
          <div
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(Math.min(100, paidPercent))}
            aria-label={`پیشرفت تسویه ${debt.counterparty}`}
            className="h-2.5 w-full overflow-hidden rounded-pill bg-surface-muted"
          >
            <div
              className={[
                'h-full rounded-pill transition-[width] duration-300',
                debt.is_overdue ? 'bg-critical-500' : debt.is_settled ? 'bg-positive-500' : 'bg-brand-500',
              ].join(' ')}
              style={{ width: `${Math.min(100, paidPercent)}%` }}
            />
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border pt-3.5 text-[11.5px] text-ink-soft">
          <span className="flex items-center gap-1.5">
            <Calendar className="size-3.5 text-ink-faint" aria-hidden="true" />
            {'ایجاد: '}
            <span>{debt.issued_on_display}</span>
          </span>
          <span className="flex items-center gap-1.5">
            <Calendar className="size-3.5 text-ink-faint" aria-hidden="true" />
            {'سررسید: '}
            <span className={debt.is_overdue ? 'font-medium text-critical-600' : ''}>
              {debt.due_on_display}
            </span>
          </span>
          {debt.due_relative && !debt.is_settled ? (
            <span className={debt.is_overdue ? 'text-critical-600' : 'text-ink-faint'}>
              {debt.due_relative}
            </span>
          ) : null}
        </div>

        {debt.description ? (
          <p className="mt-3 rounded-control bg-surface-muted px-3 py-2.5 text-[12px] leading-6 text-ink-soft">
            {debt.description}
          </p>
        ) : null}
      </Card>

      {/* Actions */}
      <div className="mb-4 flex flex-wrap gap-2">
        {!debt.is_settled && remaining > 0 ? (
          <Button
            onClick={openPayment}
            leadingIcon={<Plus className="size-4" aria-hidden="true" />}
            className="flex-1"
          >
            {debt.direction === 'payable' ? 'ثبت پرداخت' : 'ثبت دریافت'}
          </Button>
        ) : null}
        <Button variant="secondary" onClick={() => setIsEditOpen(true)} className="flex-1">
          ویرایش اطلاعات
        </Button>
      </div>

      {/* Payment history */}
      <Card padded={false}>
        <div className="border-b border-border px-4 py-3.5 sm:px-5">
          <h2 className="text-[15px] font-semibold text-ink">
            {debt.direction === 'payable' ? 'پرداخت‌ها' : 'دریافت‌ها'}
          </h2>
          <p className="mt-0.5 text-xs text-ink-faint">
            <span className="ltr-nums">{formatDigits(debt.payments_count)}</span>
            {' مورد ثبت شده'}
          </p>
        </div>

        {debt.payments.length === 0 ? (
          <EmptyState
            icon={<Wallet className="size-6" aria-hidden="true" />}
            title={
              debt.direction === 'payable'
                ? 'هنوز پرداختی ثبت نشده است'
                : 'هنوز دریافتی ثبت نشده است'
            }
            description="هر پرداخت را جداگانه ثبت کنید تا پیشرفت تسویه دقیق محاسبه شود."
          />
        ) : (
          <ul className="divide-y divide-border">
            {[...debt.payments]
              .sort((a, b) => b.paid_on.localeCompare(a.paid_on))
              .map((payment) => (
                <li key={payment.id} className="flex items-center gap-3 px-4 py-3 sm:px-5">
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-control bg-positive-50 text-positive-600">
                    <Wallet className="size-4" aria-hidden="true" />
                  </span>

                  <div className="min-w-0 flex-1">
                    <p className="text-[13px] font-medium text-ink">
                      <MoneyDisplay value={payment.amount} />
                    </p>
                    <p className="mt-0.5 text-[11px] text-ink-faint">
                      {formatRelativeDay(payment.paid_on)}
                      {payment.account_name ? ` • ${payment.account_name}` : ''}
                    </p>
                    {payment.note ? (
                      <p className="mt-0.5 truncate text-[11px] text-ink-faint">{payment.note}</p>
                    ) : null}
                  </div>

                  <button
                    type="button"
                    onClick={() =>
                      removePayment.mutate(
                        { debtId, paymentId: payment.id },
                        { onSuccess: () => showToast({ message: 'پرداخت حذف شد.' }) },
                      )
                    }
                    disabled={removePayment.isPending}
                    aria-label="حذف این پرداخت"
                    className="flex size-9 shrink-0 items-center justify-center rounded-control text-ink-faint transition-colors hover:bg-critical-50 hover:text-critical-600 disabled:opacity-50"
                  >
                    <Trash2 className="size-3.5" aria-hidden="true" />
                  </button>
                </li>
              ))}
          </ul>
        )}
      </Card>

      {/* Danger zone */}
      <div className="mt-4 rounded-card border border-border bg-surface p-4">
        {confirmDelete ? (
          <div className="flex flex-col gap-3">
            <p className="text-[12.5px] leading-6 text-ink-soft">
              با حذف این مورد، تمام پرداخت‌های ثبت‌شده آن نیز حذف می‌شود. این کار قابل بازگشت نیست.
            </p>
            <div className="flex gap-2">
              <Button
                variant="danger"
                onClick={() =>
                  deleteDebt.mutate(debtId, { onSuccess: () => navigate('/debts') })
                }
                isLoading={deleteDebt.isPending}
                className="flex-1"
              >
                حذف قطعی
              </Button>
              <Button variant="ghost" onClick={() => setConfirmDelete(false)} className="flex-1">
                انصراف
              </Button>
            </div>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setConfirmDelete(true)}
            className="text-[12.5px] font-medium text-critical-600 hover:text-critical-700"
          >
            حذف این مورد
          </button>
        )}
      </div>

      {/* Payment form */}
      <ResponsiveDialog
        open={isPaymentOpen}
        onClose={() => setIsPaymentOpen(false)}
        title={debt.direction === 'payable' ? 'ثبت پرداخت' : 'ثبت دریافت'}
        description={`باقی‌مانده: ${debt.remaining_display}`}
        footer={
          <div className="flex gap-2">
            <Button variant="ghost" onClick={() => setIsPaymentOpen(false)} className="flex-1">
              انصراف
            </Button>
            <Button
              onClick={submitPayment}
              isLoading={addPayment.isPending || isSubmitting}
              className="flex-[2]"
            >
              ثبت
            </Button>
          </div>
        }
      >
        <form onSubmit={submitPayment} noValidate className="space-y-4">
          <Input
            label="مبلغ (تومان)"
            inputMode="numeric"
            dir="ltr"
            value={paymentAmount}
            onChange={(event) => {
              const latin = toLatinDigits(event.target.value).replace(/[^\d]/g, '')
              setValue('amount', latin, { shouldValidate: false })
            }}
            error={errors.amount?.message}
            hint={
              paymentAmount
                ? `معادل: ${formatDigits(Number(normalizeNumericInput(paymentAmount)) || 0)} تومان`
                : undefined
            }
          />

          <JalaliDatePicker
            label="تاریخ"
            value={paidOn}
            onChange={(iso) => setValue('paid_on', iso, { shouldValidate: true })}
            error={errors.paid_on?.message}
            disableFuture
          />

          <Input
            label="توضیح"
            placeholder="مثلاً قسط پنجم"
            error={errors.note?.message}
            {...register('note')}
          />

          {actionError ? (
            <p role="alert" className="rounded-control bg-critical-50 px-3 py-2 text-xs text-critical-700">
              {actionError}
            </p>
          ) : null}
        </form>
      </ResponsiveDialog>

      <DebtForm
        open={isEditOpen}
        debt={debt}
        onClose={() => setIsEditOpen(false)}
      />
    </>
  )
}
