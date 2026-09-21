/**
 * Chart colours, per theme.
 *
 * Recharts takes concrete colour values (SVG presentation attributes cannot
 * resolve `var(--…)`), so the palette lives here as TypeScript constants
 * that mirror the theme tokens in `index.css`. When a token changes, change
 * the matching entry here — the two files reference each other in comments
 * so the pairing is hard to miss.
 */
import { useTheme } from '../hooks/useTheme'

export interface ChartPalette {
  /** Gridlines. */
  grid: string
  /** Axis tick text. */
  tick: string
  /** Donut slice separation stroke — matches the card surface. */
  stroke: string
  /** The primary series / line colour. */
  brand: string
  /** Income series. */
  income: string
  /** Expense series. */
  expense: string
}

export const LIGHT_CHART: ChartPalette = {
  grid: '#e8eaee', // --color-border
  tick: '#667085', // --color-ink-faint
  stroke: '#ffffff', // --color-surface
  brand: '#3566e8', // --color-brand-500
  income: '#12a150', // --color-positive-500
  expense: '#3566e8', // --color-brand-500
}

export const DARK_CHART: ChartPalette = {
  grid: '#2a2f3a', // dark --color-border
  tick: '#818a9b', // dark --color-ink-faint
  stroke: '#171a21', // dark --color-surface
  brand: '#5b8bfb', // dark --color-brand-500
  income: '#22b45f', // dark --color-positive-500
  expense: '#5b8bfb', // dark --color-brand-500
}

/** The palette matching the active theme. */
export function useChartPalette(): ChartPalette {
  const { theme } = useTheme()
  return theme === 'dark' ? DARK_CHART : LIGHT_CHART
}
