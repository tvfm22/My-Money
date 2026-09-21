import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { useDialogA11y } from './useDialogA11y'

export interface ModalProps {
  open: boolean
  onClose: () => void
  title?: ReactNode
  description?: ReactNode
  children: ReactNode
  footer?: ReactNode
  size?: 'sm' | 'md' | 'lg'
}

const SIZES = {
  sm: 'max-w-sm',
  md: 'max-w-lg',
  lg: 'max-w-2xl',
} as const

/**
 * A centred dialog for desktop.
 *
 * On small screens the shared `ResponsiveDialog` wrapper swaps this for a
 * bottom sheet, which is the correct mobile pattern and puts the controls
 * within thumb reach.
 *
 * Focus handling (initial focus, Tab cycling, `Escape`, focus restore) lives
 * in `useDialogA11y` and is shared with `BottomSheet`.
 */
export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = 'md',
}: ModalProps) {
  const panelRef = useDialogA11y(open, onClose)

  if (!open) return null

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-4">
      <div
        className="absolute inset-0 bg-scrim backdrop-blur-[2px] animate-fade-in"
        onClick={onClose}
        aria-hidden="true"
      />

      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === 'string' ? title : undefined}
        tabIndex={-1}
        className={[
          'relative z-10 flex max-h-[92vh] w-full flex-col bg-surface shadow-overlay',
          'rounded-t-card sm:rounded-card animate-slide-up sm:animate-fade-rise',
          'outline-none',
          SIZES[size],
        ]
          .filter(Boolean)
          .join(' ')}
      >
        {title ? (
          <header className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
            <div className="min-w-0">
              <h2 className="text-base font-semibold text-ink">{title}</h2>
              {description ? (
                <p className="mt-0.5 text-xs leading-5 text-ink-faint">{description}</p>
              ) : null}
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label="بستن"
              className="-me-1 flex size-11 shrink-0 items-center justify-center rounded-control text-ink-faint transition-colors hover:bg-surface-muted hover:text-ink"
            >
              <X className="size-4" aria-hidden="true" />
            </button>
          </header>
        ) : null}

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-4">
          {children}
        </div>

        {footer ? (
          <footer className="border-t border-border px-5 py-3.5 pb-[max(0.875rem,env(safe-area-inset-bottom))]">
            {footer}
          </footer>
        ) : null}
      </div>
    </div>,
    document.body,
  )
}
