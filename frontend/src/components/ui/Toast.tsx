import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import type { ReactNode } from 'react'
import { CheckCircle2, X } from 'lucide-react'

/**
 * The single place success and undo feedback is rendered.
 *
 * The app previously had no success surface at all — a save just closed its
 * sheet, and the only evidence anything happened was the list quietly
 * updating. Toasts make completion explicit and carry the *undo* affordance
 * for destructive actions (a delete can be reversed for a few seconds without
 * a confirmation dialog standing in the way of the common path).
 *
 * Rendered through a portal at the end of `<body>`, anchored above the mobile
 * bottom navigation, announced through a polite live region, and
 * self-dismissing after a few seconds.
 */

export interface ToastOptions {
  message: string
  /** `error` toasts live longer — the user needs time to read them. */
  tone?: 'success' | 'error'
  /** Optional reversible action, e.g. «بازگردانی» after a delete. */
  action?: { label: string; onClick: () => void }
}

interface ToastEntry extends ToastOptions {
  id: number
}

interface ToastContextValue {
  showToast: (options: ToastOptions) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

/** Access the toast surface. Must be used under `<ToastProvider>`. */
export function useToast(): ToastContextValue {
  const context = useContext(ToastContext)
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider')
  }
  return context
}

const SUCCESS_VISIBLE_MS = 4500
const ERROR_VISIBLE_MS = 7000

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastEntry[]>([])
  const nextId = useRef(1)

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])

  const showToast = useCallback(
    (options: ToastOptions) => {
      const id = nextId.current++
      setToasts((current) => [...current.slice(-2), { ...options, id }])
    },
    [],
  )

  const value = useMemo(() => ({ showToast }), [showToast])

  return (
    <ToastContext.Provider value={value}>
      {children}

      {/* aria-live so a screen reader announces the outcome of a save or a
          delete even though focus never moved. */}
      <div
        aria-live="polite"
        className="pointer-events-none fixed inset-x-0 bottom-[calc(4.75rem+env(safe-area-inset-bottom))] z-[60] flex flex-col items-center gap-2 px-4 lg:bottom-6"
      >
        {toasts.map((toast) => (
          <ToastCard
            key={toast.id}
            toast={toast}
            onDismiss={() => dismiss(toast.id)}
          />
        ))}
      </div>
    </ToastContext.Provider>
  )
}

function ToastCard({ toast, onDismiss }: { toast: ToastEntry; onDismiss: () => void }) {
  const isError = toast.tone === 'error'
  const visibleFor = isError ? ERROR_VISIBLE_MS : SUCCESS_VISIBLE_MS

  useEffect(() => {
    const timer = window.setTimeout(onDismiss, visibleFor)
    return () => window.clearTimeout(timer)
  }, [onDismiss, visibleFor])

  return (
    <div
      role="status"
      className={[
        'animate-fade-rise pointer-events-auto flex w-full max-w-sm items-center gap-2.5 rounded-card border px-3.5 py-2.5 shadow-overlay',
        // Surfaces stay token-driven so the toast reads correctly in both
        // themes; the icon and border carry the tone.
        isError
          ? 'border-critical-100 bg-critical-50 text-critical-700'
          : 'border-border bg-surface text-ink',
      ].join(' ')}
    >
      {!isError ? (
        <CheckCircle2 className="size-4 shrink-0 text-positive-600" aria-hidden="true" />
      ) : null}

      <p className={['min-w-0 flex-1 text-[12.5px] leading-5', isError ? '' : 'font-medium'].join(' ')}>
        {toast.message}
      </p>

      {toast.action ? (
        <button
          type="button"
          onClick={() => {
            toast.action?.onClick()
            onDismiss()
          }}
          className="shrink-0 rounded-control px-2 py-1 text-[12px] font-semibold text-brand-600 transition-colors hover:text-brand-700"
        >
          {toast.action.label}
        </button>
      ) : null}

      <button
        type="button"
        onClick={onDismiss}
        aria-label="بستن"
        className={[
          'flex size-8 shrink-0 items-center justify-center rounded-control transition-colors',
          isError ? 'text-critical-600 hover:bg-critical-100' : 'text-ink-faint hover:bg-surface-muted',
        ].join(' ')}
      >
        <X className="size-3.5" aria-hidden="true" />
      </button>
    </div>
  )
}
