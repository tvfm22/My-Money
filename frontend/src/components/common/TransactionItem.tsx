import { ArrowDownLeft, ArrowUpRight } from 'lucide-react'
import type { Transaction } from '../../types'
import { CategoryIcon } from './CategoryIcon'
import { MoneyDisplay } from './MoneyDisplay'
import { formatRelativeDay } from '../../utils/jalali'

export interface TransactionItemProps {
  transaction: Transaction
  onClick?: (transaction: Transaction) => void
  /** Show the account name as a secondary line. */
  showAccount?: boolean
  className?: string
}

/**
 * A single transaction row.
 *
 * Built as a card-shaped row rather than a table cell so it survives the
 * narrowing to a phone width without a horizontal scroll — the spec asks for
 * cards instead of wide tables.
 *
 * The direction of the money is conveyed by three independent cues: the icon
 * (arrow in/out), the colour, and the explicit `+`/`−` sign, so colour is
 * never the only signal.
 */
export function TransactionItem({
  transaction,
  onClick,
  showAccount = false,
  className = '',
}: TransactionItemProps) {
  const isIncome = transaction.transaction_type === 'income'
  const category = transaction.category_detail

  const secondary = [category?.name, showAccount ? transaction.account_name : null]
    .filter(Boolean)
    .join(' • ')

  const content = (
    <>
      <CategoryIcon
        name={category?.icon}
        color={category?.color}
        size="md"
        filled
      />

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className="truncate text-[13.5px] font-medium text-ink">
            {transaction.title || category?.name || 'تراکنش'}
          </span>
          {transaction.tags.length > 0 ? (
            <span className="flex shrink-0 items-center gap-0.5 text-ink-faint">
              {transaction.tags.slice(0, 2).map((tag) => (
                <span
                  key={tag.id}
                  className="rounded-pill px-1.5 py-0.5 text-[10px]"
                  style={{ backgroundColor: `${tag.color}1a`, color: tag.color }}
                >
                  {tag.name}
                </span>
              ))}
            </span>
          ) : null}
        </div>

        <div className="mt-0.5 flex items-center gap-1.5 text-[11.5px] text-ink-faint">
          <span className="truncate">{secondary || 'بدون دسته‌بندی'}</span>
          {transaction.date_display ? (
            <>
              <span aria-hidden="true">·</span>
              <span className="shrink-0">{formatRelativeDay(transaction.occurred_on)}</span>
            </>
          ) : null}
        </div>
      </div>

      <MoneyDisplay
        value={isIncome ? transaction.amount : `-${transaction.amount}`}
        signed
        className={[
          'shrink-0 text-[13.5px] font-semibold',
          isIncome ? 'text-positive-600' : 'text-ink',
        ].join(' ')}
      />
    </>
  )

  const classes = [
    'flex w-full items-center gap-3 rounded-card border border-border bg-surface p-3 text-start',
    onClick ? 'cursor-pointer transition-colors active:bg-surface-muted hover:bg-surface-muted/60' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ')

  if (onClick) {
    return (
      <button type="button" onClick={() => onClick(transaction)} className={classes}>
        {content}
      </button>
    )
  }

  return <div className={classes}>{content}</div>
}

/** The direction glyph used by the quick-entry toggle and filter chips. */
export function TransactionTypeIcon({ type }: { type: 'income' | 'expense' }) {
  if (type === 'income') return <ArrowDownLeft className="size-4" aria-hidden="true" />
  return <ArrowUpRight className="size-4" aria-hidden="true" />
}
