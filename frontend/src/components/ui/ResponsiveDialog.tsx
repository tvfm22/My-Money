import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { Modal } from './Modal'
import { BottomSheet } from './BottomSheet'

export interface ResponsiveDialogProps {
  open: boolean
  onClose: () => void
  title?: ReactNode
  description?: ReactNode
  children: ReactNode
  footer?: ReactNode
  size?: 'sm' | 'md' | 'lg'
}

/** True below Tailwind's `sm` breakpoint (640px). */
function useIsCompact(): boolean {
  const [compact, setCompact] = useState(() =>
    typeof window === 'undefined' ? false : window.innerWidth < 640,
  )

  useEffect(() => {
    const query = window.matchMedia('(max-width: 639px)')
    const update = () => setCompact(query.matches)
    update()
    query.addEventListener('change', update)
    return () => query.removeEventListener('change', update)
  }, [])

  return compact
}

/**
 * One dialog API, two presentations: a bottom sheet on phones (thumb-reachable,
 * the native-feeling pattern) and a centred modal on larger screens.
 *
 * Every form in the app uses this rather than choosing for itself, so the
 * mobile behaviour is consistent by construction.
 */
export function ResponsiveDialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = 'md',
}: ResponsiveDialogProps) {
  const isCompact = useIsCompact()

  if (isCompact) {
    return (
      <BottomSheet open={open} onClose={onClose} title={title} description={description} footer={footer}>
        {children}
      </BottomSheet>
    )
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      description={description}
      footer={footer}
      size={size}
    >
      {children}
    </Modal>
  )
}
