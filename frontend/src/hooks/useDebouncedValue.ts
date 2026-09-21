import { useEffect, useState } from 'react'

/**
 * Returns `value` after it has been stable for `delay` milliseconds.
 *
 * Used by the transaction search box so the API is asked once the user pauses,
 * not once per keystroke. The input keeps rendering the immediate value (it
 * stays responsive) while the *query* consumes the debounced one.
 */
export function useDebouncedValue<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay)
    return () => window.clearTimeout(timer)
  }, [value, delay])

  return debounced
}
