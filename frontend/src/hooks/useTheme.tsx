import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'
import type { ReactNode } from 'react'

export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'mymoney.theme'

const THEME_COLORS: Record<Theme, string> = {
  light: '#f7f8fa',
  dark: '#0f1115',
}

function readStoredTheme(): Theme | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    return raw === 'light' || raw === 'dark' ? raw : null
  } catch {
    return null
  }
}

function systemTheme(): Theme {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

interface ThemeContextValue {
  theme: Theme
  setTheme: (theme: Theme) => void
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

/** Access the active theme. Must be used under `<ThemeProvider>`. */
export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider')
  }
  return context
}

/**
 * Owns the light/dark decision.
 *
 * The choice persists in localStorage and falls back to the OS preference on
 * first visit. The `.dark` class on `<html>` is what actually drives the
 * colours: every token in `index.css` is redefined under it, so switching the
 * class re-skins the whole app without touching a single component. The
 * browser UI colour (`meta[name=theme-color]`) follows along.
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => readStoredTheme() ?? systemTheme())

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')

    const meta = document.querySelector('meta[name="theme-color"]')
    if (meta) meta.setAttribute('content', THEME_COLORS[theme])

    try {
      window.localStorage.setItem(STORAGE_KEY, theme)
    } catch {
      // A blocked or full localStorage must never break theming.
    }
  }, [theme])

  const setTheme = useCallback((next: Theme) => setThemeState(next), [])

  const value = useMemo(() => ({ theme, setTheme }), [theme, setTheme])

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}
