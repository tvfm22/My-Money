import { Loader2, Wallet } from 'lucide-react'

/**
 * Shown while the app resolves whether the visitor has a valid session.
 *
 * This exists so the first paint is never a blank screen and never a flash of
 * the login form for a user who is, in fact, signed in.
 */
export function FullPageLoader() {
  return (
    <div
      className="flex min-h-dvh flex-col items-center justify-center gap-4 bg-canvas"
      role="status"
      aria-live="polite"
    >
      <span className="flex size-12 items-center justify-center rounded-card bg-brand-600 text-white">
        <Wallet className="size-6" aria-hidden="true" />
      </span>
      <p className="flex items-center gap-2 text-[13px] text-ink-soft">
        <Loader2 className="size-4 animate-spin" aria-hidden="true" />
        در حال آماده‌سازی…
      </p>
    </div>
  )
}
