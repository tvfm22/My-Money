/**
 * Persian number, money and percentage formatting.
 *
 * ## Numeral policy
 *
 * Digits are rendered in **Latin** (`۰۱۲۳` → `0123`) throughout the product.
 * Persian text, the Jalali calendar and the `تومان` unit are all still used —
 * only the glyphs for 0-9 differ.
 *
 * This is deliberate and reversed an earlier decision. Persian-Indic digits
 * look right in a sentence but are hard to scan in a column of money, cannot be
 * compared at a glance in a table, and are awkward to type into a numeric
 * field. Latin digits also match what the user's keyboard and bank statements
 * show, which matters more on a finance screen than typographic purity.
 *
 * The switch lives here rather than at ~40 call sites so there is exactly one
 * place to change it back. Pass `latin: false` to opt an individual value back
 * into Persian digits.
 *
 * The server already sends pre-formatted display strings for money
 * (`amount_display`, `budgeted_display`, ...), and those are translated on the
 * way in by `latinize()` below, so the two sides can never disagree.
 */

const PERSIAN_DIGITS = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹'] as const

/** Arabic-Indic digits, which some keyboards and pasted text produce. */
const ARABIC_DIGITS = ['٠', '١', '٢', '٣', '٤', '٥', '٦', '٧', '٨', '٩'] as const

/** The product-wide numeral style. Flip to `true` for Persian glyphs. */
export const USE_PERSIAN_DIGITS = false

/** U+066C ARABIC THOUSANDS SEPARATOR — the correct Persian grouping glyph. */
export const THOUSANDS_SEPARATOR = '\u066c'

/** U+066B ARABIC DECIMAL SEPARATOR — the Persian radix point. */
export const DECIMAL_SEPARATOR = '\u066b'

/** The currency unit. Kept as a constant so a future multi-currency build has
 *  one place to change. */
export const CURRENCY_UNIT = 'تومان'

/**
 * The zero glyph an empty money field shows, in the product's numeral style.
 *
 * A `placeholder="۰"` typed literally into JSX bypasses every formatter, so it
 * kept rendering a Persian glyph long after the numeral switch flipped. Using
 * this constant (and `formatDigits` for anything dynamic) keeps input fields
 * consistent with the figures they hold — a form that shows a Persian zero and
 * then a Latin `250,000` the moment you type reads as a bug.
 */
export const ZERO_PLACEHOLDER = USE_PERSIAN_DIGITS ? '۰' : '0'

/**
 * The minimum password length, formatted for display.
 *
 * It exists so the rule is stated in a validation message in the same numeral
 * style as the rest of the interface. The numeric bound (8) lives in the Zod
 * schema; this is only its rendering, and the two are asserted to agree by the
 * form tests.
 */
export const MIN_PASSWORD = formatNumber(8, { decimals: 0 })

/**
 * Format a calendar year, in the product's numeral style and **never grouped**.
 *
 * A year is an identifier, not a quantity: `1405` is correct and `1,405` is
 * nonsense. This is why years cannot go through `formatDigits`, whose whole job
 * is to insert grouping separators — that produced `شهریور ۱٬۴۰۵` the moment
 * the numeral style became Latin.
 *
 * Years are also never negative or fractional, so no sign or decimal handling is
 * needed; the digits are converted one at a time.
 */
export function formatYear(year: number | string): string {
  const text = String(year).trim()
  return USE_PERSIAN_DIGITS ? toPersianDigits(text) : text
}

/**
 * Rewrite a server display string into the product's chosen numeral style.
 *
 * The backend formats money with Persian digits *and* Persian separators
 * (`۲۵۰٬۰۰۰ تومان`), so digits alone are not enough — U+066C has to become a
 * comma too, otherwise the result is `250٬000`, the worst of both worlds.
 *
 * Only glyphs are touched: the numeric value is never re-parsed or re-rounded,
 * so the client and server can never disagree about an amount. Persian words
 * (`تومان`, `میلیون`, month names) pass through unchanged.
 */
export function latinize(value: string): string {
  if (USE_PERSIAN_DIGITS) return value
  return toLatinDigits(value)
    .replace(new RegExp(THOUSANDS_SEPARATOR, 'g'), ',')
    .replace(new RegExp(DECIMAL_SEPARATOR, 'g'), '.')
}

/** Convert Latin digits to Persian. */
export function toPersianDigits(value: string | number): string {
  return String(value).replace(/[0-9]/g, (d) => PERSIAN_DIGITS[Number(d)])
}

/** Normalise Persian and Arabic-Indic digits back to Latin. */
export function toLatinDigits(value: string): string {
  return value
    .replace(/[۰-۹]/g, (d) => String(PERSIAN_DIGITS.indexOf(d as never)))
    .replace(/[٠-٩]/g, (d) => String(ARABIC_DIGITS.indexOf(d as never)))
}

/**
 * Strip everything a user might type as grouping or decoration from a numeric
 * string, leaving a value `Number()` can parse. Accepts Persian digits, both
 * thousands separators, and a Persian decimal separator.
 */
export function normalizeNumericInput(value: string): string {
  return toLatinDigits(value)
    // U+2212 MINUS SIGN is what `formatMoney` emits, so it must round-trip.
    .replace(/\u2212/g, '-')
    .replace(/[\u066c\u060c,\s]/g, '')
    .replace(/\u066b/g, '.')
    .replace(/[^\d.-]/g, '')
}

interface FormatNumberOptions {
  /** Decimal places to show. Trailing zeros are trimmed unless `fixed` is set. */
  decimals?: number
  /** Keep exactly `decimals` digits, including trailing zeros. */
  fixed?: boolean
  /** Emit Latin digits instead of Persian. Useful for `<input>` values. */
  latin?: boolean
}

/**
 * Format a number with Persian grouping.
 *
 * Examples (with the default Latin numeral style):
 *   formatNumber(1234567)                -> '1,234,567'
 *   formatNumber(1500.5)                 -> '1,500.5'
 *   formatNumber(1234567, {latin:false}) -> '۱٬۲۳۴٬۵۶۷'
 */
export function formatNumber(
  value: number | string | null | undefined,
  options: FormatNumberOptions = {},
): string {
  const { decimals = 2, fixed = false, latin = !USE_PERSIAN_DIGITS } = options

  const numeric = typeof value === 'number' ? value : Number(normalizeNumericInput(String(value ?? '')))

  if (!Number.isFinite(numeric)) {
    return latin ? '0' : '۰'
  }

  // Round to the requested precision *first*, then split. Splitting before
  // rounding would take the integer part from the unrounded value (1500.5
  // with 1 decimal would render as ۱٬۵۰۱٫۵ instead of ۱٬۵۰۰٫۵).
  const rounded = Number(numeric.toFixed(decimals))
  const isInteger = Number.isInteger(rounded)

  let [integerPart, fractionPart = ''] = Math.abs(rounded).toFixed(decimals).split('.')

  if (!fixed) {
    // Trim trailing zeros so whole Toman amounts never render as `۲۵۰٬۰۰۰٫۰۰`.
    fractionPart = isInteger ? '' : fractionPart.replace(/0+$/, '')
  }

  const sign = rounded < 0 ? '-' : ''
  const separator = latin ? ',' : THOUSANDS_SEPARATOR
  const decimalPoint = latin ? '.' : DECIMAL_SEPARATOR

  const grouped = integerPart.replace(/\B(?=(\d{3})+(?!\d))/g, separator)
  const body = fractionPart ? `${grouped}${decimalPoint}${fractionPart}` : grouped
  const signed = `${sign}${body}`

  return latin ? signed : toPersianDigits(signed)
}

interface FormatMoneyOptions extends FormatNumberOptions {
  /** Append the currency unit. Default true. */
  withUnit?: boolean
  /** Show a leading + or − sign for non-negative/negative values. */
  signed?: boolean
}

/**
 * The one helper every grouped-digit display should use.
 *
 * Call sites used to write `toPersianDigits(value.toLocaleString('en-US'))`,
 * which produced Persian digits wrapped around a *Latin* comma — visually
 * inconsistent with `formatNumber`/`formatMoney`, which emit U+066C. This is
 * the single entry point for "grouped digits", and it follows the product-wide
 * numeral style (`USE_PERSIAN_DIGITS`).
 */
export function formatDigits(value: number | string | null | undefined): string {
  return formatNumber(value, { decimals: 0 })
}

/** Force Persian-Indic digits for a specific value, whatever the global style.
 *  Used for the Jalali calendar, where the month grid is read as a calendar
 *  rather than scanned as data. */
export function formatDigitsPersian(value: number | string | null | undefined): string {
  return formatNumber(value, { decimals: 0, latin: false })
}

/** Same as {@link formatDigits} but keeps Latin digits and commas, for
 *  values that go straight into an `<input>` or a test assertion. */
export function formatDigitsLatin(value: number | string | null | undefined): string {
  return formatNumber(value, { decimals: 0, latin: true })
}

/**
 * Recursively rewrite Persian/Arabic-Indic digits in every string of a payload.
 *
 * The backend builds its `*_display` strings with Persian digits. Rather than
 * touch ~50 render sites — and risk missing the one added tomorrow — the
 * translation happens once, on the way out of the HTTP client. The value is
 * never re-computed, only its digits are transliterated, so a rounding
 * difference cannot be introduced between the two sides.
 *
 * Only strings that actually contain Persian digits are rebuilt, and the walk
 * is short-circuited for everything else, so a large paginated payload is not
 * copied needlessly. Non-plain objects (Date, File, Blob) are passed through
 * untouched — rebuilding those would corrupt them.
 */
export function latinizeDeep<T>(value: T): T {
  if (USE_PERSIAN_DIGITS) return value

  if (typeof value === 'string') {
    return hasPersianDigits(value) ? (latinize(value) as unknown as T) : value
  }

  if (Array.isArray(value)) {
    let changed = false
    const next = value.map((item) => {
      const mapped = latinizeDeep(item)
      if (mapped !== item) changed = true
      return mapped
    })
    // Identity matters here: TanStack Query compares payloads structurally, so
    // a fresh array on every response would re-render every consumer of it.
    return (changed ? next : value) as unknown as T
  }

  if (value !== null && typeof value === 'object') {
    // Leave anything that is not a plain object alone. A Date, FormData entry
    // or Blob reaching here would be destroyed by a shallow rebuild.
    const proto = Object.getPrototypeOf(value)
    if (proto !== Object.prototype && proto !== null) return value

    const source = value as Record<string, unknown>
    let changed = false
    const result: Record<string, unknown> = {}
    for (const [key, item] of Object.entries(source)) {
      const next = latinizeDeep(item)
      if (next !== item) changed = true
      result[key] = next
    }
    // Return the original reference when nothing changed, so React Query's
    // structural sharing still sees a stable object.
    return (changed ? result : value) as T
  }

  return value
}

/** Persian/Arabic-Indic digits plus the two Persian separators. A string of
 *  only separators (`abc٬def`) still needs rewriting, so the digits alone are
 *  not a sufficient test. */
const PERSIAN_NUMERAL_RE = /[\u06F0-\u06F9\u0660-\u0669\u066c\u066b]/

/** True when a string contains anything `latinize` would rewrite. */
export function hasPersianDigits(value: string): boolean {
  return PERSIAN_NUMERAL_RE.test(value)
}

/**
 * Format an amount of money the way the product spec requires.
 *
 * Examples (with the default Latin numeral style):
 *   formatMoney(250000)                -> '250,000 تومان'
 *   formatMoney(-250000)               -> '−250,000 تومان'
 *   formatMoney(250000, {signed:true}) -> '+250,000 تومان'
 */
export function formatMoney(
  value: number | string | null | undefined,
  options: FormatMoneyOptions = {},
): string {
  const { withUnit = true, signed = false, ...numberOptions } = options

  const numeric = typeof value === 'number' ? value : Number(normalizeNumericInput(String(value ?? '')))
  const safe = Number.isFinite(numeric) ? numeric : 0

  // The server sends money as a decimal string with 2 dp (e.g. "250000.00").
  // Amounts are whole Toman in practice, so drop the trailing zeros.
  const text = formatNumber(Math.abs(safe), { decimals: 2, ...numberOptions })

  let sign = ''
  if (signed) {
    sign = safe > 0 ? '+' : safe < 0 ? '−' : ''
  } else if (safe < 0) {
    sign = '−'
  }

  const body = `${sign}${text}`
  return withUnit ? `${body} ${CURRENCY_UNIT}` : body
}

/**
 * A compact money label for chart axes and tight spaces.
 * 12500000 → '12.5 میلیون', 1200000000 → '1.2 میلیارد'
 */
export function formatMoneyCompact(
  value: number | string | null | undefined,
  options: { latin?: boolean } = {},
): string {
  const numeric = typeof value === 'number' ? value : Number(normalizeNumericInput(String(value ?? '')))
  const safe = Number.isFinite(numeric) ? numeric : 0

  const abs = Math.abs(safe)
  const sign = safe < 0 ? '−' : ''
  const { latin = !USE_PERSIAN_DIGITS } = options

  // The scale word stays Persian whatever the numeral style: `12.5 میلیون`
  // reads as Persian with Latin digits, whereas `12.5 M` silently switches the
  // interface language. The `latin` option only ever controls the digits.
  const render = (n: number, suffix: string) => {
    const rounded = n >= 100 ? Math.round(n) : Number(n.toFixed(1))
    return `${sign}${formatNumber(rounded, { decimals: 1, latin })} ${suffix}`
  }

  if (abs >= 1_000_000_000) return render(abs / 1_000_000_000, 'میلیارد')
  if (abs >= 1_000_000) return render(abs / 1_000_000, 'میلیون')
  if (abs >= 1_000) return render(abs / 1_000, 'هزار')

  // Below a thousand, "980" alone is ambiguous next to scaled figures like
  // "1.2 میلیون" — say the unit once so the column stays comparable.
  return `${sign}${formatNumber(abs, { decimals: 0, latin })} ${CURRENCY_UNIT}`
}

/**
 * Format a percentage with the Persian percent sign.
 *
 * Examples (with the default Latin numeral style):
 *   formatPercent(65)     -> '65%'
 *   formatPercent(65.4, 1) -> '65.4%'
 */
export function formatPercent(
  value: number | string | null | undefined,
  decimals = 0,
  options: { latin?: boolean } = {},
): string {
  const numeric = typeof value === 'number' ? value : Number(normalizeNumericInput(String(value ?? '')))
  const safe = Number.isFinite(numeric) ? numeric : 0
  const latin = options.latin ?? !USE_PERSIAN_DIGITS
  const text = formatNumber(safe, { decimals, latin })
  return `${text}${latin ? '%' : '٪'}`
}

/**
 * Format a signed percentage change, e.g. '+12%' / '−5%'.
 * Returns a neutral placeholder when the change is undefined (a jump from
 * zero has no meaningful percentage).
 */
export function formatPercentChange(
  value: number | null | undefined,
  decimals = 0,
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return '—'
  }
  const sign = value > 0 ? '+' : value < 0 ? '−' : ''
  const latin = !USE_PERSIAN_DIGITS
  return `${sign}${formatNumber(Math.abs(value), { decimals, latin })}${latin ? '%' : '٪'}`
}

/**
 * Format a plain count, e.g. transaction counts. Never shows decimals.
 */
export function formatCount(value: number | null | undefined): string {
  return formatNumber(value ?? 0, { decimals: 0 })
}

/**
 * Format the numeric value for an `<input>` while the user types: grouped,
 * but in Latin digits so the field stays easy to edit and re-parse.
 */
export function formatAmountForInput(value: string | number): string {
  const normalized = normalizeNumericInput(String(value ?? ''))
  if (!normalized) return ''

  const negative = normalized.startsWith('-')
  const [integerPart = '', fractionPart] = normalized.replace('-', '').split('.')

  const grouped = integerPart.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  const sign = negative ? '-' : ''
  return fractionPart !== undefined ? `${sign}${grouped}.${fractionPart}` : `${sign}${grouped}`
}
