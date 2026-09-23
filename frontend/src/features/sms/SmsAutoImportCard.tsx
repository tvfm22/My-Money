import { useEffect, useId, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { CheckCircle2, ClipboardPaste, MessageSquareText, RefreshCw } from 'lucide-react'

import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Card } from '../../components/ui/Card'
import { Skeleton } from '../../components/ui/Skeleton'
import { useToast } from '../../components/ui/Toast'
import { useSetSmsAutoImport, useSmsAutoImport, useSmsSync } from '../../hooks/queries'
import { errorMessage } from '../../services/client'
import { formatCount } from '../../utils/format'
import type { SmsAutoImportState, SmsSyncResult } from '../../types'

/**
 * Automatic message reading, on the transactions screen.
 *
 * ## What "automatic" can honestly mean here
 *
 * Reading the phone's inbox is an operating-system capability: it needs a
 * permission the platform grants to an *installed app*, not to a web page.
 * There is no browser API for it. So this card does not ask for an SMS
 * permission, because there is none to ask for — a prompt that could not be
 * honoured would be worse than no prompt, and the one thing this screen must
 * not do is imply the app can see messages it cannot.
 *
 * What it controls instead is the half a web app *can* own: whether the app
 * looks for unrecorded messages on its own, or only when the user asks. Turned
 * off, no automatic pass runs — the manual action keeps working, because the
 * user pressing a button is not the thing they switched off.
 *
 * ## Two states, not three
 *
 * The brief asks for enabled / disabled / permission-not-granted. There is no
 * third state here to show, so there is no third badge: an invented "دسترسی
 * داده نشده" would describe a permission that does not exist. The switch is
 * the whole story, and the status line always says which of the two it is.
 *
 * ## Where the messages come from
 *
 * The user supplies the text. That is the only route in, and the card says so
 * in one line rather than leaving the user to guess why nothing arrives.
 */
export function SmsAutoImportCard() {
  const { data: state, isPending, isError, error, refetch, isFetching } = useSmsAutoImport()
  const setAutoImport = useSetSmsAutoImport()
  const sync = useSmsSync()
  const { showToast } = useToast()

  const [isOpen, setIsOpen] = useState(false)
  const [text, setText] = useState('')
  const [lastResult, setLastResult] = useState<SmsSyncResult | null>(null)

  /**
   * The automatic pass: once per visit, and only while the switch is on.
   *
   * Held in a ref rather than in state because it is a one-shot side effect,
   * not something the screen renders — putting it in state would re-render the
   * page and could re-trigger itself. The ref also makes the "off" behaviour
   * observable: with the switch off this effect returns immediately and no
   * request is made at all.
   */
  const hasAutoChecked = useRef(false)
  const runSync = useRef(sync.mutate)
  runSync.current = sync.mutate

  useEffect(() => {
    if (!state?.enabled || hasAutoChecked.current) return
    hasAutoChecked.current = true
    runSync.current({})
  }, [state?.enabled])

  const handleToggle = (enabled: boolean) => {
    setAutoImport.mutate(enabled, {
      onError: (err) => showToast({ message: errorMessage(err), tone: 'error' }),
    })
  }

  const handleManualCheck = () => {
    const trimmed = text.trim()
    sync.mutate(trimmed ? { text: trimmed } : {}, {
      onSuccess: (result) => {
        setLastResult(result)
        // The text is cleared only after it has been read: if the request
        // failed, the user's paste is still on screen to retry with.
        if (result.summary.new_transactions > 0) setText('')
        showToast({ message: result.message })
      },
      onError: (err) => showToast({ message: errorMessage(err), tone: 'error' }),
    })
  }

  return (
    <Card className="mb-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <MessageSquareText className="size-4 shrink-0 text-ink-soft" aria-hidden="true" />
            <h2 className="text-[14px] font-semibold text-ink">
              دریافت خودکار تراکنش‌ها از پیامک
            </h2>
            {state ? (
              <Badge variant={state.enabled ? 'positive' : 'neutral'} size="sm">
                {state.enabled ? 'فعال' : 'غیرفعال'}
              </Badge>
            ) : null}
          </div>
          <p className="mt-1 text-[11.5px] leading-5 text-ink-soft">
            {state
              ? state.message
              : 'برای خواندن تراکنش‌های بانکی، متن پیامک‌ها را همین‌جا وارد می‌کنید.'}
          </p>
        </div>

        {state ? (
          <AutoImportSwitch
            enabled={state.enabled}
            isBusy={setAutoImport.isPending}
            onToggle={handleToggle}
          />
        ) : null}
      </div>

      {isError ? (
        <p role="alert" className="mt-3 text-xs text-critical-600">
          {errorMessage(error, 'وضعیت دریافت خودکار خوانده نشد.')}{' '}
          <button
            type="button"
            onClick={() => void refetch()}
            disabled={isFetching}
            className="font-medium text-brand-600 hover:text-brand-700"
          >
            تلاش دوباره
          </button>
        </p>
      ) : isPending ? (
        <AutoImportSkeleton />
      ) : (
        <>
          <Counts state={state} />
          <ManualCheck
            isOpen={isOpen}
            onToggle={() => setIsOpen((current) => !current)}
            text={text}
            onTextChange={setText}
            onRun={handleManualCheck}
            isRunning={sync.isPending}
            result={lastResult}
          />
        </>
      )}
    </Card>
  )
}

// ---------------------------------------------------------------------------

function AutoImportSkeleton() {
  return (
    <div className="mt-3 space-y-2" role="status" aria-busy="true">
      <span className="sr-only">در حال خواندن وضعیت دریافت خودکار…</span>
      <Skeleton className="h-3.5 w-40 rounded-full" />
      <Skeleton className="h-3.5 w-28 rounded-full" />
    </div>
  )
}

/**
 * A real switch: `role="switch"` with `aria-checked`, so a screen reader
 * announces the state instead of just "button". The label is on the control
 * itself rather than on a sibling, because the visible title is a heading, not
 * this control's label.
 */
function AutoImportSwitch({
  enabled,
  isBusy,
  onToggle,
}: {
  enabled: boolean
  isBusy: boolean
  onToggle: (enabled: boolean) => void
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      aria-label="دریافت خودکار تراکنش‌ها از پیامک"
      disabled={isBusy}
      onClick={() => onToggle(!enabled)}
      className={[
        'relative inline-flex h-6 w-11 shrink-0 items-center rounded-pill border transition-colors duration-150',
        'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500',
        enabled ? 'border-brand-600 bg-brand-600' : 'border-border-strong bg-surface-muted',
        isBusy ? 'opacity-60' : '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <span
        aria-hidden="true"
        className={[
          'size-5 rounded-full bg-white shadow-card transition-transform duration-150',
          // RTL: "on" moves the knob towards the start edge, which is the
          // right-hand side. Translating on the inline axis keeps that
          // automatic instead of hard-coding a direction.
          enabled ? 'translate-x-[-1.375rem]' : 'translate-x-[-0.125rem]',
        ].join(' ')}
      />
    </button>
  )
}

/** The counts, and when the last check ran. */
function Counts({ state }: { state: SmsAutoImportState }) {
  const { imported_from_sms_count: imported, pending_count: pending } = state

  return (
    <dl className="mt-3 grid grid-cols-2 gap-2 rounded-control border border-border bg-surface-muted p-3">
      <div>
        <dt className="text-[11px] text-ink-faint">از پیامک وارد شده</dt>
        <dd className="mt-0.5 text-[13px] font-semibold text-ink">
          <span className="ltr-nums">{formatCount(imported)}</span> تراکنش
        </dd>
      </div>
      <div>
        <dt className="text-[11px] text-ink-faint">در انتظار بررسی</dt>
        <dd className="mt-0.5 text-[13px] font-semibold text-ink">
          {pending > 0 ? (
            <Link to="/sms" className="text-brand-600 hover:text-brand-700">
              <span className="ltr-nums">{formatCount(pending)}</span> تراکنش
            </Link>
          ) : (
            <span className="ltr-nums">{formatCount(0)} تراکنش</span>
          )}
        </dd>
      </div>
      <div className="col-span-2 border-t border-border pt-2">
        <dt className="text-[11px] text-ink-faint">آخرین بررسی</dt>
        <dd className="mt-0.5 text-[12px] text-ink-soft">
          {state.last_checked_label ? (
            <span className="ltr-nums">{state.last_checked_label}</span>
          ) : (
            'هنوز بررسی نشده'
          )}
        </dd>
      </div>
    </dl>
  )
}

/**
 * The manual action, and the result of the last one.
 *
 * The panel is a disclosure rather than a separate screen: reading older
 * messages is something done *while looking at the ledger*, and navigating away
 * would lose the user's place in it.
 */
function ManualCheck({
  isOpen,
  onToggle,
  text,
  onTextChange,
  onRun,
  isRunning,
  result,
}: {
  isOpen: boolean
  onToggle: () => void
  text: string
  onTextChange: (value: string) => void
  onRun: () => void
  isRunning: boolean
  result: SmsSyncResult | null
}) {
  const panelId = useId()

  return (
    <div className="mt-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant="secondary"
          leadingIcon={<RefreshCw className="size-4" aria-hidden="true" />}
          aria-expanded={isOpen}
          aria-controls={panelId}
          onClick={onToggle}
        >
          خواندن پیامک‌های قبلی
        </Button>
        {result ? (
          <span role="status" className="text-[11.5px] leading-5 text-ink-soft">
            {result.message}
          </span>
        ) : null}
      </div>

      {isOpen ? (
        <div id={panelId} className="mt-3 flex flex-col gap-2">
          <label htmlFor={`${panelId}-text`} className="text-[12.5px] font-medium text-ink-soft">
            پیامک‌های بانکی
          </label>
          <textarea
            id={`${panelId}-text`}
            value={text}
            onChange={(event) => onTextChange(event.target.value)}
            rows={5}
            dir="rtl"
            placeholder="پیامک‌های قبلی را همین‌جا بچسبانید…"
            className={[
              'w-full resize-y rounded-control border bg-surface px-3 py-2.5 text-sm leading-6 text-ink',
              'transition-colors duration-150 placeholder:text-ink-faint',
              'border-border-strong focus:border-brand-500 focus:outline-none',
            ].join(' ')}
          />
          <p className="text-[11px] leading-5 text-ink-faint">
            پیامک‌هایی که قبلاً خوانده شده‌اند دوباره ثبت نمی‌شوند؛ فقط موارد تازه اضافه
            می‌شود. متن پیامک‌ها جایی ارسال نمی‌شود.
          </p>

          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              leadingIcon={<ClipboardPaste className="size-4" aria-hidden="true" />}
              isLoading={isRunning}
              onClick={onRun}
            >
              بررسی پیامک‌ها
            </Button>
            {result?.batch_id ? (
              <Link
                to={`/sms/batches/${result.batch_id}`}
                className="inline-flex items-center gap-1 text-[12px] font-medium text-brand-600 hover:text-brand-700"
              >
                <CheckCircle2 className="size-3.5" aria-hidden="true" />
                بررسی تراکنش‌های تازه
              </Link>
            ) : null}
          </div>

          {result ? <CheckResult result={result} /> : null}
        </div>
      ) : null}
    </div>
  )
}

/**
 * The three numbers, laid out the way the question was asked: how many were
 * looked at, how many were new, how many added nothing.
 */
function CheckResult({ result }: { result: SmsSyncResult }) {
  const { checked, new_transactions: created, without_new: withoutNew } = result.summary

  return (
    <ul className="flex flex-col gap-1 rounded-control border border-border bg-surface-muted p-3 text-[12px] text-ink-soft">
      <li>
        <span className="ltr-nums">{formatCount(checked)}</span> پیامک بررسی شد
      </li>
      <li className={created > 0 ? 'font-medium text-positive-700' : undefined}>
        {created > 0 ? (
          <>
            <span className="ltr-nums">{formatCount(created)}</span> تراکنش جدید پیدا شد
          </>
        ) : (
          'تراکنش جدیدی پیدا نشد'
        )}
      </li>
      {withoutNew > 0 ? (
        <li>
          <span className="ltr-nums">{formatCount(withoutNew)}</span> پیامک تراکنش جدیدی
          نداشت
        </li>
      ) : null}
    </ul>
  )
}
