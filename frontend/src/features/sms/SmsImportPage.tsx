import { useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { BellOff, ClipboardPaste, Eye, Inbox, Trash2 } from 'lucide-react'

import { Button } from '../../components/ui/Button'
import { Card, CardHeader } from '../../components/ui/Card'
import { Badge } from '../../components/ui/Badge'
import { EmptyState } from '../../components/ui/EmptyState'
import { ErrorState } from '../../components/ui/ErrorState'
import { Input } from '../../components/ui/Input'
import { Select } from '../../components/ui/Select'
import { LoadingState } from '../../components/ui/LoadingState'
import { MoneyDisplay } from '../../components/common/MoneyDisplay'
import { useToast } from '../../components/ui/Toast'
import {
  useAccounts,
  useCreateSmsBatch,
  useDeleteSmsBatch,
  useDismissSmsReminder,
  useSmsBatches,
  useSmsParsePreview,
  useSmsReminder,
} from '../../hooks/queries'
import { errorMessage } from '../../services/client'
import { formatCount, formatYear } from '../../utils/format'
import { JALALI_MONTHS, currentJalaliMonth } from '../../utils/jalali'
import type { SmsImportBatchSummary, SmsParsePayload } from '../../types'

/** Badge tone per staged status — every badge also carries its own label. */
const BATCH_STATUS_VARIANT: Record<SmsImportBatchSummary['status'], 'brand' | 'positive'> = {
  reviewing: 'brand',
  committed: 'positive',
}

/**
 * The import screen: paste last month's bank messages, read what was found,
 * stage a batch, then head to the review screen.
 *
 * Reading and staging are two separate calls by design — `/parse/` writes
 * nothing, so the preview can be discarded without leaving rows behind, and
 * only «ثبت برای بررسی» stores anything (and even that lands in the staging
 * tables, not the ledger).
 */
export function SmsImportPage() {
  const navigate = useNavigate()
  const { showToast } = useToast()

  const { data: reminder } = useSmsReminder()
  const { data: batchesData, isPending, isError, error, refetch, isFetching } = useSmsBatches()
  const { data: accounts } = useAccounts()
  const preview = useSmsParsePreview()
  const createBatch = useCreateSmsBatch()
  const deleteBatch = useDeleteSmsBatch()
  const dismissReminder = useDismissSmsReminder()

  const [text, setText] = useState('')
  const [accountId, setAccountId] = useState('')
  const [sourceLabel, setSourceLabel] = useState('')
  const [periodYear, setPeriodYear] = useState('')
  const [periodMonth, setPeriodMonth] = useState('')
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<number | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const batches = batchesData?.results ?? []
  const currentYear = currentJalaliMonth().year

  const buildPayload = (): SmsParsePayload => ({
    text: text.trim(),
    source_label: sourceLabel.trim() || undefined,
    account: accountId ? Number(accountId) : undefined,
    period_year: periodYear ? Number(periodYear) : undefined,
    period_month: periodMonth ? Number(periodMonth) : undefined,
  })

  const handlePreview = () => {
    if (!text.trim()) return
    preview.mutate(buildPayload())
  }

  const handleStage = () => {
    if (!text.trim()) return
    createBatch.mutate(buildPayload(), {
      onSuccess: (batch) => {
        showToast({ message: `${formatCount(batch.counts.total)} پیامک برای بررسی ثبت شد.` })
        navigate(`/sms/batches/${batch.id}`)
      },
      onError: (err) => showToast({ message: errorMessage(err), tone: 'error' }),
    })
  }

  const handleDelete = (id: number) => {
    deleteBatch.mutate(id, {
      onSuccess: () => {
        setConfirmingDeleteId(null)
        showToast({ message: 'دسته پیامک حذف شد.' })
      },
      onError: (err) => showToast({ message: errorMessage(err), tone: 'error' }),
    })
  }

  return (
    <>
      <div className="mb-4">
        <h1 className="text-lg font-bold text-ink lg:text-xl">وارد کردن پیامک بانکی</h1>
        <p className="mt-1 text-[12.5px] text-ink-soft">
          پیامک‌های بانک را بچسبانید تا تراکنش‌ها خوانده و برای بررسی آماده شود
        </p>
      </div>

      {/* Monthly reminder — the server decides when it applies. */}
      {reminder?.should_remind ? (
        <div
          role="status"
          className="mb-4 flex flex-wrap items-center gap-3 rounded-card border border-brand-100 bg-brand-50 p-4"
        >
          <ClipboardPaste className="size-5 shrink-0 text-brand-600" aria-hidden="true" />
          <p className="min-w-0 flex-1 text-[13px] leading-6 text-ink">{reminder.message}</p>
          <div className="flex shrink-0 gap-2">
            <Button size="sm" onClick={() => textareaRef.current?.focus()}>
              وارد کردن
            </Button>
            <Button
              size="sm"
              variant="ghost"
              leadingIcon={<BellOff className="size-4" aria-hidden="true" />}
              isLoading={dismissReminder.isPending}
              onClick={() =>
                dismissReminder.mutate(
                  { year: reminder.suggested_year, month: reminder.suggested_month },
                  { onError: (err) => showToast({ message: errorMessage(err), tone: 'error' }) },
                )
              }
            >
              نمایش نده
            </Button>
          </div>
        </div>
      ) : null}

      {/* Paste form */}
      <Card className="mb-4">
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="sms-paste" className="text-[13px] font-medium text-ink-soft">
              پیامک‌ها
            </label>
            <textarea
              id="sms-paste"
              ref={textareaRef}
              value={text}
              onChange={(event) => setText(event.target.value)}
              rows={7}
              dir="rtl"
              placeholder={
                'مثال:\nبانک ملت: خرید کارت ... مبلغ 250,000 ریال ... موجودی 12,000,000 ریال'
              }
              className={[
                'w-full resize-y rounded-control border bg-surface px-3 py-2.5 text-sm leading-6 text-ink',
                'transition-colors duration-150 placeholder:text-ink-faint',
                'border-border-strong focus:border-brand-500 focus:outline-none',
              ].join(' ')}
            />
            <p className="text-xs text-ink-faint">
              پیامک‌ها را همان‌طور که هستند بچسبانید؛ ترتیب و پیام‌های غیرتراکنشی مهم نیست.
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <Select
              label="حساب"
              placeholder="حساب مرتبط"
              value={accountId}
              onChange={(event) => setAccountId(event.target.value)}
              options={(accounts?.results ?? []).map((account) => ({
                value: String(account.id),
                label: account.name,
              }))}
              hint="برای تطبیق موجودی لازم است"
            />
            <Select
              label="ماه"
              placeholder="ماه گذشته"
              value={periodMonth}
              onChange={(event) => setPeriodMonth(event.target.value)}
              options={JALALI_MONTHS.map((name, index) => ({
                value: String(index + 1),
                label: name,
              }))}
            />
            <Select
              label="سال"
              placeholder="سال جاری"
              value={periodYear}
              onChange={(event) => setPeriodYear(event.target.value)}
              options={[0, 1, 2].map((offset) => ({
                value: String(currentYear - offset),
                label: formatYear(currentYear - offset),
              }))}
            />
          </div>

          <Input
            label="برچسب منبع"
            placeholder="مثلاً: بانک ملت"
            value={sourceLabel}
            onChange={(event) => setSourceLabel(event.target.value)}
            maxLength={120}
          />

          {preview.isError ? (
            <p role="alert" className="text-xs text-critical-600">
              {errorMessage(preview.error)}
            </p>
          ) : null}

          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              leadingIcon={<Eye className="size-4" aria-hidden="true" />}
              isLoading={preview.isPending}
              disabled={!text.trim()}
              onClick={handlePreview}
            >
              پیش‌نمایش
            </Button>
            <Button
              leadingIcon={<ClipboardPaste className="size-4" aria-hidden="true" />}
              isLoading={createBatch.isPending}
              disabled={!text.trim()}
              onClick={handleStage}
            >
              ثبت برای بررسی
            </Button>
          </div>
        </div>
      </Card>

      {/* Preview panel — nothing here has been stored. */}
      {preview.data ? (
        <Card className="mb-4">
          <CardHeader
            title={`پیش‌نمایش ${preview.data.period.label}`}
            subtitle={`${formatCount(preview.data.summary.total)} پیام خوانده شد؛ ${formatCount(preview.data.summary.readable)} تراکنش قابل ثبت`}
            action={
              <Badge variant={preview.data.summary.low_confidence ? 'caution' : 'info'} size="sm">
                {preview.data.summary.low_confidence
                  ? `${formatCount(preview.data.summary.low_confidence)} مورد نیازمند بررسی`
                  : 'خواندن بدون نگرانی'}
              </Badge>
            }
          />
          <ul className="mt-3 flex flex-col gap-2">
            {preview.data.messages.map((message, index) => (
              <li
                key={`${message.fingerprint}-${index}`}
                className="rounded-control border border-border bg-surface-muted p-3"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[13px] font-semibold text-ink">
                    {message.bank_label || 'بانک نامشخص'}
                  </span>
                  <Badge size="sm" variant={message.is_transaction ? 'info' : 'neutral'}>
                    {message.is_transaction ? 'تراکنش' : 'پیام غیرتراکنشی'}
                  </Badge>
                  {message.is_transaction ? (
                    <span className="ltr-nums text-[13px] font-medium text-ink">
                      <MoneyDisplay value={message.amount} withUnit />
                    </span>
                  ) : null}
                </div>
                {message.warnings.length ? (
                  <p className="mt-1.5 text-[11.5px] leading-5 text-caution-700">
                    {message.warnings.join(' • ')}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      {/* Import history */}
      <h2 className="mb-3 text-[15px] font-semibold text-ink">دسته‌های پیشین</h2>
      {isError ? (
        <ErrorState
          message={errorMessage(error)}
          onRetry={() => void refetch()}
          isRetrying={isFetching}
        />
      ) : isPending ? (
        <LoadingState />
      ) : batches.length === 0 ? (
        <EmptyState
          icon={<Inbox aria-hidden="true" />}
          title="هنوز دسته‌ای ثبت نشده"
          description="پیامک‌های بانکی خود را در کادر بالا بچسبانید تا اولین دسته ساخته شود."
        />
      ) : (
        <ul className="flex flex-col gap-3">
          {batches.map((batch) => (
            <li key={batch.id} className="rounded-card border border-border bg-surface p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-[14px] font-semibold text-ink">{batch.period_label}</h3>
                    <Badge variant={BATCH_STATUS_VARIANT[batch.status]} size="sm">
                      {batch.status_label}
                    </Badge>
                    {batch.source_label ? (
                      <span className="text-[11.5px] text-ink-faint">{batch.source_label}</span>
                    ) : null}
                  </div>
                  <p className="mt-1 text-[11.5px] leading-5 text-ink-soft">
                    {formatCount(batch.counts.imported)} ثبت‌شده
                    {' • '}
                    {formatCount(batch.counts.pending)} در انتظار بررسی
                    {batch.counts.skipped
                      ? ` • ${formatCount(batch.counts.skipped)} رد شده`
                      : ''}
                    {batch.counts.duplicate
                      ? ` • ${formatCount(batch.counts.duplicate)} تکراری`
                      : ''}
                    {batch.account_name ? ` • ${batch.account_name}` : ''}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  <Link
                    to={`/sms/batches/${batch.id}`}
                    className="text-[12px] font-medium text-brand-600 hover:text-brand-700"
                  >
                    بررسی
                  </Link>
                  {confirmingDeleteId === batch.id ? (
                    <>
                      <button
                        type="button"
                        onClick={() => handleDelete(batch.id)}
                        disabled={deleteBatch.isPending}
                        className="text-[12px] font-medium text-critical-600 hover:text-critical-700"
                      >
                        تأیید حذف
                      </button>
                      <button
                        type="button"
                        onClick={() => setConfirmingDeleteId(null)}
                        className="text-[12px] text-ink-faint hover:text-ink"
                      >
                        انصراف
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setConfirmingDeleteId(batch.id)}
                      aria-label={`حذف دسته ${batch.period_label}`}
                      className="flex items-center gap-1 text-[12px] text-ink-soft hover:text-critical-600"
                    >
                      <Trash2 className="size-3.5" aria-hidden="true" />
                      حذف
                    </button>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}