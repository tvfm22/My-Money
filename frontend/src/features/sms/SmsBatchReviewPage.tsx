import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowRight, CheckCircle2, Scale } from 'lucide-react'

import { Button } from '../../components/ui/Button'
import { Card, CardHeader } from '../../components/ui/Card'
import { Badge } from '../../components/ui/Badge'
import { ErrorState } from '../../components/ui/ErrorState'
import { Select } from '../../components/ui/Select'
import { LoadingState } from '../../components/ui/LoadingState'
import { useToast } from '../../components/ui/Toast'
import {
  useAccounts,
  useApplySmsReconcile,
  useBulkUpdateSmsItems,
  useCategoryPicker,
  useCommitSmsBatch,
  useSmsBatch,
  useSmsReconcile,
  useUpdateSmsBatch,
} from '../../hooks/queries'
import { errorMessage } from '../../services/client'
import { formatCount } from '../../utils/format'
import { SmsItemCard } from './SmsItemCard'

// SMS-REVIEW-STATE

/**
 * The review screen for one staged batch.
 *
 * Every decision here is a PATCH on a staged row; the ledger is only written
 * by «ثبت در دفتر», which stays out of reach while rows are still undecided.
 */
export function SmsBatchReviewPage() {
  const { id } = useParams()
  const batchId = Number(id)
  const { showToast } = useToast()

  const { data: batch, isPending, isError, error, refetch, isFetching } = useSmsBatch(batchId)
  const { data: accounts } = useAccounts()
  const { data: expenseCategories } = useCategoryPicker('expense')
  const { data: incomeCategories } = useCategoryPicker('income')
  const { data: reconciliation } = useSmsReconcile(batchId)

  const commit = useCommitSmsBatch(batchId)
  const bulkUpdate = useBulkUpdateSmsItems(batchId)
  const applyReconcile = useApplySmsReconcile(batchId)
  const updateBatch = useUpdateSmsBatch(batchId)

  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [bulkCategory, setBulkCategory] = useState('')

  const items = batch?.items ?? []
  const pendingCount = batch?.counts.pending ?? 0
  const isCommitted = batch?.status === 'committed'

  const toggleSelected = (itemId: number) => {
    setSelectedIds((current) =>
      current.includes(itemId) ? current.filter((value) => value !== itemId) : [...current, itemId],
    )
  }

  const handleBulk = (payload: { category?: number; status?: 'skipped' }) => {
    if (selectedIds.length === 0) return
    bulkUpdate.mutate(
      { item_ids: selectedIds, ...payload },
      {
        onSuccess: (result) => {
          showToast({ message: `${formatCount(result.updated_count)} قلم به‌روزرسانی شد.` })
          setSelectedIds([])
          setBulkCategory('')
        },
        onError: (err) => showToast({ message: errorMessage(err), tone: 'error' }),
      },
    )
  }

  const handleCommit = () => {
    commit.mutate(undefined, {
      onSuccess: (result) => {
        showToast({ message: result.message || 'ثبت تراکنش‌ها انجام شد.' })
      },
      onError: (err) => showToast({ message: errorMessage(err), tone: 'error' }),
    })
  }

  const handleApplyReconcile = () => {
    applyReconcile.mutate(undefined, {
      onSuccess: (result) =>
        showToast({ message: result.message || 'موجودی اولیه حساب به‌روزرسانی شد.' }),
      onError: (err) => showToast({ message: errorMessage(err), tone: 'error' }),
    })
  }

  const handleAccountChange = (value: string) => {
    updateBatch.mutate(
      { account: value ? Number(value) : null },
      { onError: (err) => showToast({ message: errorMessage(err), tone: 'error' }) },
    )
  }

  // SMS-REVIEW-JSX
  if (Number.isNaN(batchId)) {
    return <ErrorState title="دسته پیدا نشد" message="آدرس این صفحه کامل نیست." />
  }

  return (
    <>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <Link
            to="/sms"
            className="mb-1 inline-flex items-center gap-1 text-[12px] text-ink-faint hover:text-ink"
          >
            <ArrowRight className="size-3.5" aria-hidden="true" />
            بازگشت به وارد کردن
          </Link>
          <h1 className="text-lg font-bold text-ink lg:text-xl">
            بررسی {batch?.period_label ?? 'دسته پیامک'}
          </h1>
          {batch ? (
            <p className="mt-1 text-[12.5px] text-ink-soft">
              {formatCount(batch.counts.pending)} در انتظار بررسی
              {' • '}
              {formatCount(batch.counts.imported)} ثبت‌شده
              {batch.counts.skipped ? ` • ${formatCount(batch.counts.skipped)} رد شده` : ''}
              {batch.counts.duplicate ? ` • ${formatCount(batch.counts.duplicate)} تکراری` : ''}
              {batch.counts.noise ? ` • ${formatCount(batch.counts.noise)} غیرتراکنشی` : ''}
            </p>
          ) : null}
        </div>

        <div className="flex shrink-0 flex-col items-end gap-2">
          <Select
            aria-label="حساب این دسته"
            placeholder="حساب مرتبط"
            value={batch?.account ? String(batch.account) : ''}
            onChange={(event) => handleAccountChange(event.target.value)}
            options={(accounts?.results ?? []).map((account) => ({
              value: String(account.id),
              label: account.name,
            }))}
            containerClassName="w-44"
            disabled={isCommitted}
          />
          {isCommitted ? (
            <Badge variant="positive" size="sm">
              ثبت‌شده در دفتر
            </Badge>
          ) : (
            <Button
              size="sm"
              leadingIcon={<CheckCircle2 className="size-4" aria-hidden="true" />}
              isLoading={commit.isPending}
              disabled={pendingCount === 0}
              onClick={handleCommit}
            >
              ثبت {formatCount(pendingCount)} قلم در دفتر
            </Button>
          )}
        </div>
      </div>

      {isError ? (
        <ErrorState
          message={errorMessage(error)}
          onRetry={() => void refetch()}
          isRetrying={isFetching}
        />
      ) : isPending ? (
        <LoadingState />
      ) : (
        <>
          {/* Bulk decision bar — appears only when something is selected. */}
          {selectedIds.length > 0 ? (
            <Card className="mb-4">
              <div className="flex flex-wrap items-end gap-3">
                <p className="text-[13px] font-medium text-ink">
                  {formatCount(selectedIds.length)} قلم انتخاب شده
                </p>
                <Select
                  aria-label="دسته‌بندی گروهی"
                  placeholder="دسته‌بندی"
                  value={bulkCategory}
                  onChange={(event) => setBulkCategory(event.target.value)}
                  options={[
                    ...(expenseCategories ?? []).map((category) => ({
                      value: `e${category.id}`,
                      label: category.name,
                    })),
                    ...(incomeCategories ?? []).map((category) => ({
                      value: `i${category.id}`,
                      label: category.name,
                    })),
                  ]}
                  containerClassName="w-44"
                />
                <Button
                  size="sm"
                  disabled={!bulkCategory}
                  isLoading={bulkUpdate.isPending}
                  onClick={() => handleBulk({ category: Number(bulkCategory.slice(1)) })}
                >
                  اعمال دسته‌بندی
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  isLoading={bulkUpdate.isPending}
                  onClick={() => handleBulk({ status: 'skipped' })}
                >
                  رد کردن انتخاب‌ها
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setSelectedIds([])}>
                  پاک کردن انتخاب
                </Button>
              </div>
            </Card>
          ) : null}

          {items.length === 0 ? (
            <Card>
              <p className="py-6 text-center text-[13px] text-ink-soft">
                این دسته پیام قابل بررسی ندارد.
              </p>
            </Card>
          ) : (
            <ul className="flex flex-col gap-3">
              {items.map((item) => (
                <SmsItemCard
                  key={item.id}
                  item={item}
                  isSelected={selectedIds.includes(item.id)}
                  onToggleSelect={() => toggleSelected(item.id)}
                  isBulkBusy={bulkUpdate.isPending}
                  expenseCategories={expenseCategories ?? []}
                  incomeCategories={incomeCategories ?? []}
                  accounts={accounts?.results ?? []}
                />
              ))}
            </ul>
          )}

          {/* Reconciliation — what the balances printed in these messages imply. */}
          <Card className="mt-6">
            <CardHeader
              title={
                <span className="flex items-center gap-1.5">
                  <Scale className="size-4 text-ink-soft" aria-hidden="true" />
                  تطبیق موجودی
                </span>
              }
              subtitle="موجودی اعلام‌شده در پیامک‌ها با دفتر شما مقایسه می‌شود"
            />
            {reconciliation?.available ? (
              <div className="mt-3">
                <p className="text-[13px] leading-6 text-ink-soft">{reconciliation.message}</p>
                <dl className="mt-3 grid gap-3 sm:grid-cols-3">
                  <div>
                    <dt className="text-[11px] text-ink-faint">موجودی اعلام‌شده</dt>
                    <dd className="ltr-nums mt-1 text-[13px] font-semibold text-ink">
                      {reconciliation.reading_amount_display}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-[11px] text-ink-faint">موجودی اولیه نتیجه‌گیری‌شده</dt>
                    <dd className="ltr-nums mt-1 text-[13px] font-semibold text-ink">
                      {reconciliation.implied_opening_balance_display}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-[11px] text-ink-faint">اختلاف با دفتر</dt>
                    <dd
                      className={[
                        'ltr-nums mt-1 text-[13px] font-semibold',
                        reconciliation.matches ? 'text-positive-600' : 'text-caution-700',
                      ].join(' ')}
                    >
                      {reconciliation.matches ? 'اختلافی نیست' : reconciliation.drift_display}
                    </dd>
                  </div>
                </dl>
                {!reconciliation.matches && !isCommitted ? (
                  <div className="mt-3">
                    <Button
                      size="sm"
                      variant="secondary"
                      isLoading={applyReconcile.isPending}
                      onClick={handleApplyReconcile}
                    >
                      هماهنگ‌سازی موجودی اولیه حساب
                    </Button>
                  </div>
                ) : null}
              </div>
            ) : (
              <p className="mt-3 text-[13px] leading-6 text-ink-soft">
                {reconciliation?.message ??
                  'برای تطبیق موجودی، ابتدا حساب این دسته را انتخاب کنید.'}
              </p>
            )}
          </Card>
        </>
      )}
    </>
  )
}