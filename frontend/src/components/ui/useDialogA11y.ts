import { useEffect, useRef } from 'react'

/**
 * Shared dialog behaviour for `Modal` and `BottomSheet`.
 *
 * - Focus moves into the panel when it opens and returns to the element that
 *   had focus when it closes — otherwise a screen reader or keyboard user is
 *   stranded wherever the dialog left them.
 * - `Escape` closes.
 * - `Tab` cycles inside the panel. `aria-modal="true"` tells assistive tech
 *   that background content is inert, but that promise is only kept if the
 *   physical keyboard cannot tab out of the dialog.
 * - Body scroll is locked while open.
 *
 * The effect depends on `open` alone; `onClose` is read through a ref so a
 * parent re-render (a toast appearing, a query updating) cannot re-run the
 * setup and yank focus back to the panel while the user is mid-form.
 */
export function useDialogA11y(open: boolean, onClose: () => void) {
  const panelRef = useRef<HTMLDivElement>(null)
  const onCloseRef = useRef(onClose)

  useEffect(() => {
    onCloseRef.current = onClose
  })

  useEffect(() => {
    if (!open) return

    const restoreFocusTo =
      document.activeElement instanceof HTMLElement ? document.activeElement : null

    panelRef.current?.focus()

    // Everything the Tab key may land on, in DOM order. The panel itself is
    // tabIndex -1 (it receives programmatic focus only) and is excluded.
    const FOCUSABLE_SELECTOR = [
      'a[href]',
      'button:not([disabled])',
      'input:not([disabled]):not([type="hidden"])',
      'select:not([disabled])',
      'textarea:not([disabled])',
      '[tabindex]:not([tabindex="-1"])',
    ].join(', ')

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        onCloseRef.current()
        return
      }

      if (event.key !== 'Tab') return

      const panel = panelRef.current
      if (!panel) return

      const focusable = Array.from(
        panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      ).filter((element) => element.offsetParent !== null)

      if (focusable.length === 0) {
        // A dialog with no focusable children keeps the keyboard on the panel.
        event.preventDefault()
        panel.focus()
        return
      }

      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      const active = document.activeElement

      if (event.shiftKey && (active === first || active === panel)) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && active === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown)
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = previousOverflow
      restoreFocusTo?.focus()
    }
  }, [open])

  return panelRef
}
