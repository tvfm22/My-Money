import { useEffect, useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent, ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { useDialogA11y } from './useDialogA11y'

export interface BottomSheetProps {
  open: boolean
  onClose: () => void
  title?: ReactNode
  description?: ReactNode
  children: ReactNode
  footer?: ReactNode
}

/** Drag distance (px) past which a downward flick dismisses the sheet. */
const DISMISS_THRESHOLD = 90

/**
 * The mobile counterpart to `Modal` — a sheet that rises from the bottom of
 * the viewport so its controls sit within one-handed reach.
 *
 * Rendered through a portal at the end of `<body>` and the list area scrolls
 * independently of the sticky footer, so a long form never pushes the submit
 * button off screen.
 *
 * The grab area (handle + header) is a real swipe-to-dismiss surface: a
 * downward drag follows the finger and releases past the threshold. Drags
 * that start on the scrollable content are left alone so forms keep working.
 */
export function BottomSheet({
  open,
  onClose,
  title,
  description,
  children,
  footer,
}: BottomSheetProps) {
  const sheetRef = useDialogA11y(open, onClose)

  const [dragY, setDragY] = useState(0)
  const [isDragging, setIsDragging] = useState(false)
  const dragStartY = useRef<number | null>(null)

  useEffect(() => {
    if (!open) {
      setDragY(0)
      setIsDragging(false)
      dragStartY.current = null
    }
  }, [open])

  const onPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    dragStartY.current = event.clientY
    setIsDragging(true)
  }

  const onPointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (dragStartY.current === null) return
    const delta = event.clientY - dragStartY.current
    // Only a downward drag moves the sheet; upward drags are ignored.
    setDragY(Math.max(0, delta))
  }

  const endDrag = () => {
    if (dragStartY.current === null) return
    dragStartY.current = null
    setIsDragging(false)
    setDragY(0)
    if (dragY > DISMISS_THRESHOLD) onClose()
  }

  if (!open) return null

  return createPortal(
    <div className="fixed inset-0 z-50 flex flex-col justify-end">
      <div
        className="absolute inset-0 bg-scrim backdrop-blur-[2px] animate-fade-in"
        onClick={onClose}
        aria-hidden="true"
      />

      <div
        ref={sheetRef}
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === 'string' ? title : undefined}
        tabIndex={-1}
        className={[
          'relative z-10 flex max-h-[92vh] w-full flex-col rounded-t-card bg-surface shadow-overlay outline-none animate-slide-up',
          // Transform follows the finger; the release spring-back animates.
          isDragging ? '' : 'transition-transform duration-200 ease-out',
        ].join(' ')}
        style={dragY > 0 ? { transform: `translateY(${dragY}px)` } : undefined}
      >
        {/* Grab area — swiping down here dismisses the sheet. `touch-action`
            keeps the vertical gesture from turning into a page scroll. */}
        <div
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          style={{ touchAction: 'none' }}
        >
          <div className="flex justify-center pt-2.5" aria-hidden="true">
            <span className="h-1 w-10 rounded-pill bg-border-strong" />
          </div>

          {title ? (
            <header className="flex items-start justify-between gap-4 px-5 pt-3 pb-1">
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
        </div>

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
