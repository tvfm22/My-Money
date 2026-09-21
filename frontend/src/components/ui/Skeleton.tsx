export interface SkeletonProps {
  className?: string
}

/** A shimmering placeholder block. Sized entirely by the caller. */
export function Skeleton({ className = '' }: SkeletonProps) {
  return <div className={['skeleton rounded-md', className].filter(Boolean).join(' ')} aria-hidden="true" />
}
