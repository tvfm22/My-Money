import { Skeleton } from './Skeleton'

export interface LoadingStateProps {
  /** Number of skeleton rows to show. */
  rows?: number
  className?: string
}

/**
 * A generic list loading state.
 *
 * The spec is explicit that the app must never show a blank screen while data
 * is loading, so every screen renders a shaped placeholder rather than a
 * spinner in the middle of nothing.
 */
export function LoadingState({ rows = 3, className = '' }: LoadingStateProps) {
  return (
    <div
      className={['space-y-3', className].filter(Boolean).join(' ')}
      role="status"
      aria-busy="true"
      aria-live="polite"
    >
      <span className="sr-only">در حال بارگذاری…</span>
      {Array.from({ length: rows }, (_, index) => (
        <div
          key={index}
          className="flex items-center gap-3 rounded-card border border-border bg-surface p-4"
        >
          <Skeleton className="size-10 rounded-pill" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-3.5 w-1/3 rounded-full" />
            <Skeleton className="h-3 w-1/5 rounded-full" />
          </div>
          <Skeleton className="h-4 w-20 rounded-full" />
        </div>
      ))}
    </div>
  )
}

/** A single card-shaped placeholder, for dashboards and summary panels. */
export function LoadingCard({ className = '' }: { className?: string }) {
  return (
    <div
      className={['rounded-card border border-border bg-surface p-5', className]
        .filter(Boolean)
        .join(' ')}
      role="status"
      aria-busy="true"
    >
      <span className="sr-only">در حال بارگذاری…</span>
      <Skeleton className="h-3 w-24 rounded-full" />
      <Skeleton className="mt-4 h-7 w-40 rounded-lg" />
      <Skeleton className="mt-5 h-2 w-full rounded-full" />
    </div>
  )
}
