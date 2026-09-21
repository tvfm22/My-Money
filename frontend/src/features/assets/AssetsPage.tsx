import { useMemo, useState } from 'react'
import { Plus, TrendingDown, TrendingUp, Wallet } from 'lucide-react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Card, CardHeader } from '../../components/ui/Card'
import { Button } from '../../components/ui/Button'
import { Badge } from '../../components/ui/Badge'
import { EmptyState } from '../../components/ui/EmptyState'
import { ErrorState } from '../../components/ui/ErrorState'
import { LoadingCard } from '../../components/ui/LoadingState'
import { ProgressBar } from '../../components/ui/ProgressBar'
import { MoneyDisplay } from '../../components/common/MoneyDisplay'
import { AssetForm } from './AssetForm'
import { ValuationSheet } from './ValuationSheet'
import { useAssetSummary, useAssets, useNetWorthHistory } from '../../hooks/queries'
import { useChartPalette } from '../../utils/chartPalette'
import { errorMessage } from '../../services/client'
import { formatDigits, formatMoneyCompact, formatPercent } from '../../utils/format'
import type { Asset } from '../../types'

// Each asset type is drawn from a fixed pool so the palette stays calm and no
// two adjacent cards share a colour.
const TYPE_TONE: Record<string, 'brand' | 'positive' | 'caution' | 'info'> = {
  bank_account: 'brand',
  cash: 'positive',
  gold_fund: 'caution',
  gold: 'caution',
  stocks: 'info',
  currency: 'info',
  real_estate: 'brand',
  vehicle: 'info',
  deposit: 'positive',
  crypto: 'caution',
  other: 'brand',
}

/**
 * Assets and net worth.
 *
 * The screen leads with net worth (the single number that matters), then the
 * asset/liability split, then the individual holdings with their nominal
 * return. Valuations are entered by hand — the spec explicitly rules out
 * fetching live market prices.
 */
export function AssetsPage() {
  const [isFormOpen, setIsFormOpen] = useState(false)
  const [editing, setEditing] = useState<Asset | null>(null)
  const [valuing, setValuing] = useState<Asset | null>(null)

  const { data: summary, isPending: isSummaryPending } = useAssetSummary()
  const { data, isPending, isError, error, refetch, isFetching } = useAssets()
  const { data: history } = useNetWorthHistory(12)
  const palette = useChartPalette()

  const assets = data?.results ?? []

  const chartData = useMemo(
    () =>
      (history?.history ?? []).map((point) => ({
        label: point.label,
        netWorth: Number(point.net_worth),
        assets: Number(point.assets),
        liabilities: Number(point.liabilities),
      })),
    [history?.history],
  )

  const openCreate = () => {
    setEditing(null)
    setIsFormOpen(true)
  }

  return (
    <>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-bold text-ink lg:text-xl">دارایی‌ها</h1>
          <p className="mt-1 text-[12.5px] text-ink-soft">
            ارزش دارایی‌ها، بازده و روند ثروت خالص
          </p>
        </div>

        <Button
          size="sm"
          onClick={openCreate}
          leadingIcon={<Plus className="size-4" aria-hidden="true" />}
          className="shrink-0"
        >
          افزودن
        </Button>
      </div>

      {/* Net worth headline */}
      {isSummaryPending ? (
        <LoadingCard className="mb-4" />
      ) : summary ? (
        <Card className="mb-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-[12.5px] text-ink-soft">ثروت خالص</p>
              <p
                className={[
                  'mt-1.5 text-[28px] leading-tight font-bold tracking-tight lg:text-[32px]',
                  summary.net_worth.is_negative ? 'text-critical-600' : 'text-ink',
                ].join(' ')}
              >
                <MoneyDisplay value={summary.net_worth.net_worth} />
              </p>
              <p className="mt-1 text-[11.5px] text-ink-faint">
                ارزش دارایی‌ها منهای بدهی‌ها
              </p>
            </div>

            <span
              className={[
                'flex size-10 shrink-0 items-center justify-center rounded-control',
                summary.net_worth.is_negative
                  ? 'bg-critical-50 text-critical-600'
                  : 'bg-positive-50 text-positive-600',
              ].join(' ')}
            >
              <TrendingUp className="size-5" aria-hidden="true" />
            </span>
          </div>

          <dl className="mt-4 grid grid-cols-3 gap-3 border-t border-border pt-4">
            <div>
              <dt className="text-[11.5px] text-ink-faint">کل دارایی‌ها</dt>
              <dd className="mt-1 text-[13.5px] font-semibold text-ink">
                <MoneyDisplay value={summary.net_worth.total_assets} compact />
              </dd>
            </div>
            <div className="border-x border-border px-3">
              <dt className="text-[11.5px] text-ink-faint">بدهی‌ها</dt>
              <dd className="mt-1 text-[13.5px] font-semibold text-critical-600">
                <MoneyDisplay value={summary.net_worth.total_liabilities} compact />
              </dd>
            </div>
            <div>
              <dt className="text-[11.5px] text-ink-faint">طلب‌ها</dt>
              <dd className="mt-1 text-[13.5px] font-semibold text-positive-600">
                <MoneyDisplay value={summary.net_worth.total_receivables} compact />
              </dd>
            </div>
          </dl>

          {/* Nominal return across the whole portfolio */}
          {Number(summary.purchase_value) > 0 ? (
            <div className="mt-4 flex items-center justify-between gap-3 rounded-control bg-surface-muted px-3 py-2.5">
              <span className="text-[12px] text-ink-soft">بازده اسمی کل</span>
              <span className="flex items-center gap-2">
                <span className="ltr-nums text-[13px] font-semibold text-ink">
                  {summary.nominal_return_display}
                </span>
                <Badge variant={Number(summary.nominal_return) >= 0 ? 'positive' : 'critical'} size="sm">
                  <span className="ltr-nums">{summary.nominal_return_percent_display}</span>
                </Badge>
              </span>
            </div>
          ) : null}
        </Card>
      ) : null}

      {/* Net worth trend */}
      {chartData.length > 1 ? (
        <Card className="mb-4">
          <CardHeader
            title="روند ثروت خالص"
            subtitle={`در ${formatDigits(12)} ماه گذشته`}
          />
          <div className="mt-4 h-52 w-full" dir="ltr">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
                <defs>
                  <linearGradient id="netWorthFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={palette.brand} stopOpacity={0.22} />
                    <stop offset="100%" stopColor={palette.brand} stopOpacity={0.02} />
                  </linearGradient>
                </defs>

                <CartesianGrid strokeDasharray="3 3" stroke={palette.grid} vertical={false} />
                <XAxis
                  dataKey="label"
                  tick={{ fontSize: 10, fill: palette.tick }}
                  axisLine={false}
                  tickLine={false}
                  reversed
                />
                <YAxis
                  tick={{ fontSize: 10, fill: palette.tick }}
                  axisLine={false}
                  tickLine={false}
                  orientation="right"
                  width={54}
                  tickFormatter={(value: number) => formatMoneyCompact(value, { latin: true })}
                />
                <Tooltip
                  content={<NetWorthTooltip />}
                  cursor={{ stroke: palette.grid }}
                />
                <Area
                  type="monotone"
                  dataKey="netWorth"
                  stroke={palette.brand}
                  strokeWidth={2}
                  fill="url(#netWorthFill)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>
      ) : null}

      {/* Breakdown by type */}
      {summary && summary.by_type.length > 0 ? (
        <Card className="mb-4">
          <CardHeader title="ترکیب دارایی‌ها" subtitle="سهم هر نوع از کل ارزش" />
          <div className="mt-4 space-y-3">
            {summary.by_type.map((row) => {
              const total = Number(summary.current_value) || 1
              const percent = (Number(row.total) / total) * 100

              return (
                <div key={row.type}>
                  <div className="mb-1.5 flex items-baseline justify-between gap-2">
                    <span className="text-[12.5px] text-ink-soft">{row.type}</span>
                    <span className="flex items-center gap-2">
                      <span className="ltr-nums text-[12px] font-medium text-ink">{row.display}</span>
                      <span className="ltr-nums text-[11px] text-ink-faint">
                        {formatPercent(percent)}
                      </span>
                    </span>
                  </div>
                  <ProgressBar
                    value={percent}
                    tone={TYPE_TONE[row.type] ?? 'brand'}
                    size="sm"
                    label={`سهم ${row.type}`}
                  />
                </div>
              )
            })}
          </div>
        </Card>
      ) : null}

      {/* Holdings */}
      {isError ? (
        <ErrorState
          compact
          message={errorMessage(error, 'فهرست دارایی‌ها دریافت نشد.')}
          onRetry={() => void refetch()}
          isRetrying={isFetching}
        />
      ) : isPending ? (
        <LoadingCard />
      ) : assets.length === 0 ? (
        <Card padded={false}>
          <EmptyState
            icon={<Wallet className="size-6" aria-hidden="true" />}
            title="هنوز دارایی‌ای ثبت نشده است"
            description="حساب بانکی، طلا، سهام، ملک یا هر دارایی دیگری را ثبت کنید تا ثروت خالص شما محاسبه شود."
            action={
              <Button size="sm" onClick={openCreate}>
                افزودن دارایی
              </Button>
            }
          />
        </Card>
      ) : (
        <ul className="space-y-2.5">
          {assets.map((asset) => (
            <li key={asset.id}>
              <AssetCard
                asset={asset}
                onEdit={() => {
                  setEditing(asset)
                  setIsFormOpen(true)
                }}
                onValue={() => setValuing(asset)}
              />
            </li>
          ))}
        </ul>
      )}

      <AssetForm
        open={isFormOpen}
        asset={editing}
        onClose={() => {
          setIsFormOpen(false)
          setEditing(null)
        }}
      />

      <ValuationSheet
        asset={valuing}
        open={valuing !== null}
        onClose={() => setValuing(null)}
      />
    </>
  )
}

// ---------------------------------------------------------------------------

function AssetCard({
  asset,
  onEdit,
  onValue,
}: {
  asset: Asset
  onEdit: () => void
  onValue: () => void
}) {
  const returnPercent = Number(asset.nominal_return_percent || 0)
  const hasCost = Number(asset.purchase_value) > 0

  return (
    <div className="rounded-card border border-border bg-surface p-4">
      <div className="flex items-start gap-3">
        <span
          className={[
            'flex size-10 shrink-0 items-center justify-center rounded-control',
            asset.is_profitable ? 'bg-positive-50 text-positive-600' : 'bg-surface-muted text-ink-soft',
          ].join(' ')}
        >
          {asset.is_profitable ? (
            <TrendingUp className="size-5" aria-hidden="true" />
          ) : (
            <TrendingDown className="size-5" aria-hidden="true" />
          )}
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-[14px] font-semibold text-ink">{asset.name}</h3>
            <Badge variant="neutral" size="sm">
              {asset.asset_type_label}
            </Badge>
          </div>

          {/* The gold-fund example from the spec: units × unit price. */}
          {asset.quantity && Number(asset.quantity) > 0 ? (
            <p className="mt-1 text-[11.5px] text-ink-faint">
              <span className="ltr-nums">{formatDigits(Number(asset.quantity))}</span>
              {asset.unit ? ` ${asset.unit}` : ''}
              {asset.unit_price ? (
                <>
                  {' • هر واحد '}
                  <span className="ltr-nums">{asset.current_value_display}</span>
                </>
              ) : null}
            </p>
          ) : asset.provider ? (
            <p className="mt-1 text-[11.5px] text-ink-faint">{asset.provider}</p>
          ) : null}
        </div>

        <div className="shrink-0 text-end">
          <p className="text-[14px] font-bold text-ink">
            <MoneyDisplay value={asset.current_value} />
          </p>
          <p className="mt-0.5 text-[10.5px] text-ink-faint">ارزش فعلی</p>
        </div>
      </div>

      {hasCost ? (
        <div className="mt-3 grid grid-cols-3 gap-2 border-t border-border pt-3">
          <div>
            <p className="text-[10.5px] text-ink-faint">ارزش خرید</p>
            <p className="mt-0.5 text-[12px] font-medium text-ink-soft">
              <MoneyDisplay value={asset.purchase_value} compact />
            </p>
          </div>
          <div>
            <p className="text-[10.5px] text-ink-faint">بازده اسمی</p>
            <p
              className={[
                'mt-0.5 text-[12px] font-medium',
                asset.is_profitable ? 'text-positive-600' : 'text-critical-600',
              ].join(' ')}
            >
              <MoneyDisplay value={asset.nominal_return} compact signed />
            </p>
          </div>
          <div>
            <p className="text-[10.5px] text-ink-faint">درصد بازده</p>
            <p
              className={[
                'mt-0.5 text-[12px] font-medium ltr-nums',
                asset.is_profitable ? 'text-positive-600' : 'text-critical-600',
              ].join(' ')}
            >
              {formatPercent(returnPercent, 1)}
            </p>
          </div>
        </div>
      ) : null}

      <div className="mt-3 flex items-center justify-between gap-2 border-t border-border pt-3">
        <span className="text-[10.5px] text-ink-faint">
          {asset.last_valued_on
            ? `آخرین به‌روزرسانی: ${asset.last_valued_on.display}`
            : 'هنوز ارزش‌گذاری ثبت نشده'}
        </span>

        <div className="flex shrink-0 gap-3">
          <button
            type="button"
            onClick={onValue}
            className="text-[12px] font-medium text-brand-600 hover:text-brand-700"
          >
            به‌روزرسانی ارزش
          </button>
          <button
            type="button"
            onClick={onEdit}
            className="text-[12px] font-medium text-ink-soft hover:text-ink"
          >
            ویرایش
          </button>
        </div>
      </div>
    </div>
  )
}

function NetWorthTooltip({
  active,
  payload,
}: {
  active?: boolean
  payload?: Array<{ payload: { label: string; netWorth: number; assets: number; liabilities: number } }>
}) {
  if (!active || !payload?.length) return null
  const point = payload[0].payload

  return (
    <div className="rounded-control border border-border bg-surface px-3 py-2 shadow-raised" dir="rtl">
      <p className="text-[11.5px] font-medium text-ink">{point.label}</p>
      <p className="mt-1 text-[11.5px] text-ink-soft">
        {'ثروت خالص: '}
        <span className="ltr-nums font-semibold text-ink">
          {formatMoneyCompact(point.netWorth)}
        </span>
      </p>
      <p className="text-[11px] text-ink-faint">
        {'دارایی '}
        <span className="ltr-nums">{formatMoneyCompact(point.assets)}</span>
        {' • بدهی '}
        <span className="ltr-nums">{formatMoneyCompact(point.liabilities)}</span>
      </p>
    </div>
  )
}
