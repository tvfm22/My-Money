import { useState } from 'react'
import { ChevronDown, ChevronUp, Save, TriangleAlert } from 'lucide-react'

import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'
import { Select } from '../../components/ui/Select'
import { MoneyDisplay } from '../../components/common/MoneyDisplay'
import { useToast } from '../../components/ui/Toast'
import { useUpdateSmsItem } from '../../hooks/queries'
import { errorMessage } from '../../services/client'
import { useParams } from 'react-router-dom'
import type {
  Account,
  CategoryPickerItem,
  SmsImportItem,
  SmsItemPatch,
  SpendingType,
} from '../../types'

/** Badge tone per staged status; the label itself always travels along. */
const STATUS_VARIANT: Record<string, 'neutral' | 'caution' | 'positive' | 'critical' | 'brand'> = {
  pending: 'brand',
  imported: 'positive',
  skipped: 'neutral',
  duplicate: 'caution',
  noise: 'neutral',
}

/** Server-authored confidence labels map to fixed badge tones. */
const CONFIDENCE_VARIANT: Record<string, 'positive' | 'caution' | 'critical'> = {
  'اطمینان بالا': 'positive',
  'قابل بررسی': 'caution',
  'اطمینان کم': 'critical',
}

const SPENDING_TYPE_OPTIONS = [
  { value: 'essential', label: 'ضروری' },
  { value: 'flexible', label: 'انعطاف‌پذیر' },
  { value: 'wasted', label: 'غیرضروری' },
]

export interface SmsItemCardProps {
  item: SmsImportItem
  isSelected: boolean
  onToggleSelect: () => void
  isBulkBusy: boolean
  expenseCategories: CategoryPickerItem[]
  incomeCategories: CategoryPickerItem[]
  accounts: Account[]
}

/**
 * One staged message in the review screen.
 *
 * The original message stays next to the parsed fields on purpose — that is
 * the only way a user can tell whether «۹۸۷,۶۵۴ ریال» was read as the amount
 * or as the balance. Decisions (category, account, type, note) are edited
 * inline and saved as a single PATCH.
 */
export function SmsItemCard({
  item,
  isSelected,
  onToggleSelect,
  isBulkBusy,
  expenseCategories,
  incomeCategories,
  accounts,
}: SmsItemCardProps) {
  const { id } = useParams()
  const { showToast } = useToast()
  const updateItem = useUpdateSmsItem(Number(id))

  const [category, setCategory] = useState(item.category ? String(item.category) : '')
  const [account, setAccount] = useState(item.account ? String(item.account) : '')
  const [spendingType, setSpendingType] = useState(item.spending_type || '')
  const [note, setNote] = useState(item.note)
  const [showRaw, setShowRaw] = useState(false)

  const canDecide = item.is_transaction && (item.status === 'pending' || item.status === 'skipped')
  const isExpense = item.direction === 'expense'
  const categories = isExpense ? expenseCategories : incomeCategories

  const save = (extra: SmsItemPatch = {}) => {
    updateItem.mutate(
      {
        id: item.id,
        category: category ? Number(category) : null,
        account: account ? Number(account) : null,
        spending_type: item.direction === 'income' ? '' : (spendingType as SpendingType | ''),
        note,
        ...extra,
      },
      {
        onSuccess: () => {
          showToast({ message: 'ذخیره شد.' })
        },
        onError: (err) => showToast({ message: errorMessage(err), tone: 'error' }),
      },
    )
  }

  return (
    <li
      className={[
        'rounded-card border bg-surface p-4 transition-colors',
        isSelected ? 'border-brand-300' : 'border-border',
        item.is_transaction ? '' : 'bg-surface-muted',
      ].join(' ')}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-2.5">
          {canDecide ? (
            <input
              type="checkbox"
              checked={isSelected}
              onChange={onToggleSelect}
              aria-label={`انتخاب قلم ${item.merchant || item.bank_label}`}
              className="mt-1 size-4 shrink-0 accent-brand-600"
            />
          ) : null}
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[13px] font-semibold text-ink">
                {item.merchant || item.bank_label || 'پیامک بانکی'}
              </span>
              <Badge size="sm" variant={isExpense ? 'info' : 'positive'}>
                {item.direction_label}
              </Badge>
              {item.status !== 'pending' ? (
                <Badge size="sm" variant={STATUS_VARIANT[item.status] ?? 'neutral'}>
                  {item.status_label}
                </Badge>
              ) : null}
              <Badge size="sm" variant={CONFIDENCE_VARIANT_SAFE(item.confidence_label)}>
                {item.confidence_label}
              </Badge>
            </div>

            {/* Parsed metadata, with the honest caveats the parser sent. */}
            <p className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-ink-faint">
              {item.date_display ? (
                <span>
                  {item.date_display}
                  {item.date_assumed ? ' (تخمینی)' : ''}
                </span>
              ) : (
                <span>تاریخ خوانده نشد</span>
              )}
              {item.balance_display ? <span>موجودی: {item.balance_display}</span> : null}
              {item.card_last4 ? <span>کارت ...{item.card_last4}</span> : null}
              {item.amount_unit_assumed ? <span>واحد مبلغ تخمینی خوانده شد</span> : null}
            </p>
          </div>
        </div>

        {item.is_transaction ? (
          <div className="shrink-0 text-end">
            <span
              className={[
                'text-[14px] font-bold',
                isExpense ? 'text-ink' : 'text-positive-600',
              ].join(' ')}
            >
              <MoneyDisplay value={item.amount} withUnit />
            </span>
          </div>
        ) : null}
      </div>

      {item.warnings.length ? (
        <p className="mt-2 flex items-start gap-1.5 text-[11.5px] leading-5 text-caution-700">
          <TriangleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          {item.warnings.join(' • ')}
        </p>
      ) : null}

      <button
        type="button"
        onClick={() => setShowRaw((current) => !current)}
        aria-expanded={showRaw}
        className="mt-2 inline-flex items-center gap-1 text-[11.5px] text-ink-faint hover:text-ink"
      >
        {showRaw ? (
          <ChevronUp className="size-3.5" aria-hidden="true" />
        ) : (
          <ChevronDown className="size-3.5" aria-hidden="true" />
        )}
        {showRaw ? 'پنهان کردن پیام اصلی' : 'نمایش پیام اصلی'}
      </button>
      {showRaw ? (
        <p
          dir="rtl"
          className="mt-2 whitespace-pre-line rounded-control bg-surface-muted p-2.5 text-[11.5px] leading-6 text-ink-soft"
        >
          {item.raw_text}
        </p>
      ) : null}

      {/* Decision controls — only on rows the user can still decide about. */}
      {canDecide && !isBulkBusy ? (
        <div className="mt-3 grid gap-3 border-t border-border pt-3 sm:grid-cols-2">
          <Select
            aria-label={`دسته‌بندی ${item.merchant || item.bank_label}`}
            placeholder={isExpense ? 'دسته‌بندی هزینه' : 'دسته‌بندی درآمد'}
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            options={categories.map((entry) => ({
              value: String(entry.id),
              label: entry.name,
            }))}
          />
          <Select
            aria-label="حساب قلم"
            placeholder="حساب"
            value={account}
            onChange={(event) => setAccount(event.target.value)}
            options={accounts.map((entry) => ({
              value: String(entry.id),
              label: entry.name,
            }))}
          />
          {isExpense ? (
            <Select
              aria-label="نوع هزینه"
              placeholder="نوع هزینه"
              value={spendingType}
              onChange={(event) => setSpendingType(event.target.value)}
              options={SPENDING_TYPE_OPTIONS}
            />
          ) : null}
          <Input
            aria-label="یادداشت قلم"
            placeholder="یادداشت"
            value={note}
            onChange={(event) => setNote(event.target.value)}
          />
          <div className="flex flex-wrap items-center gap-2 sm:col-span-2">
            <Button
              size="sm"
              leadingIcon={<Save className="size-4" aria-hidden="true" />}
              isLoading={updateItem.isPending}
              onClick={() => save()}
            >
              ذخیره
            </Button>
            {item.status === 'pending' ? (
              <Button
                size="sm"
                variant="secondary"
                isLoading={updateItem.isPending}
                onClick={() => save({ status: 'skipped' })}
              >
                رد کردن
              </Button>
            ) : (
              <Button
                size="sm"
                variant="secondary"
                isLoading={updateItem.isPending}
                onClick={() => save({ status: 'pending' })}
              >
                بازگشت به بررسی
              </Button>
            )}
            {!item.is_ready ? (
              <span className="text-[11px] text-ink-faint">
                برای ثبت، دسته‌بندی لازم است.
              </span>
            ) : null}
          </div>
        </div>
      ) : null}
    </li>
  )
}

// SMS-ITEM-CARD-END

/** Unknown labels still deserve a badge; neutral keeps the rule colour-free. */
function CONFIDENCE_VARIANT_SAFE(label: string): 'positive' | 'caution' | 'critical' | 'neutral' {
  return CONFIDENCE_VARIANT[label] ?? 'neutral'
}