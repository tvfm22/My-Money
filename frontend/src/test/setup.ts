import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// Testing Library does not auto-clean when `globals` is enabled in some
// configurations, so do it explicitly to keep component tests independent.
afterEach(() => {
  cleanup()
  window.localStorage.clear()
  // Modals and bottom sheets lock body scroll while open. If a test unmounts
  // mid-effect the lock can survive into the next test, which then queries a
  // "hidden" document. Reset it defensively.
  document.body.style.overflow = ''
  document.body.innerHTML = ''
})

// jsdom implements neither of these, and several components rely on them.
if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia
}

if (!window.ResizeObserver) {
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof window.ResizeObserver
}
