import { describe, expect, it } from 'vitest'
import {
  formatCount,
  formatDigits,
  formatYear,
  formatMoney,
  formatMoneyCompact,
  formatNumber,
  formatPercent,
  formatPercentChange,
  latinize,
  latinizeDeep,
  normalizeNumericInput,
  toLatinDigits,
  toPersianDigits,
  CURRENCY_UNIT,
  USE_PERSIAN_DIGITS,
} from '../utils/format'

/**
 * These tests pin the exact strings the product asks for. Money is the one
 * place a formatting regression is a real bug, so the expectations are literal
 * rather than structural.
 *
 * ## Two numeral styles, both covered
 *
 * The product renders digits in **Latin** by default (`USE_PERSIAN_DIGITS` is
 * `false`). Every formatter therefore has two branches, and both are exercised
 * here: the default path, and the `latin: false` path that still produces the
 * Persian-Indic glyphs and the U+066C/U+066B separators.
 *
 * Both matter. The Persian path is what a future locale switch would turn on,
 * so it is not dead code — and the separators are what make
 * `normalizeNumericInput` round-trip correctly when a user pastes a number
 * copied from elsewhere in the app.
 */

describe('toPersianDigits / toLatinDigits', () => {
  it('maps every ASCII digit to its Persian counterpart', () => {
    expect(toPersianDigits('0123456789')).toBe('۰۱۲۳۴۵۶۷۸۹')
  })

  it('round-trips back to ASCII', () => {
    expect(toLatinDigits('۰۱۲۳۴۵۶۷۸۹')).toBe('0123456789')
  })

  it('also converts Arabic-Indic digits, which a Persian keyboard can emit', () => {
    expect(toLatinDigits('١٢٣')).toBe('123')
  })

  it('leaves non-digits alone', () => {
    expect(toPersianDigits('تومان 12')).toBe('تومان ۱۲')
  })
})

describe('normalizeNumericInput', () => {
  it('strips the Persian thousands separator', () => {
    expect(normalizeNumericInput('۱٬۲۳۴٬۵۶۷')).toBe('1234567')
  })

  it('strips the ASCII comma too', () => {
    expect(normalizeNumericInput('1,234,567')).toBe('1234567')
  })

  it('converts the Persian decimal separator to a dot', () => {
    expect(normalizeNumericInput('۱۲٫۵')).toBe('12.5')
  })

  it('keeps a leading minus', () => {
    expect(normalizeNumericInput('−۲۵۰')).toBe('-250')
  })
})

describe('formatNumber', () => {
  it('defaults to Latin digits with an ASCII comma', () => {
    // The product's default numeral style. Persian text and the Jalali
    // calendar are unaffected — only the glyphs for 0-9 differ.
    expect(formatNumber(123456)).toBe('123,456')
    expect(formatNumber(1234567)).toBe('1,234,567')
  })

  it('groups with U+066C when Persian digits are requested', () => {
    // U+066C ARABIC THOUSANDS SEPARATOR — ۱۲۳٬۴۵۶, not ۱۲۳,۴۵۶.
    expect(formatNumber(123456, { latin: false })).toBe('۱۲۳٬۴۵۶')
  })

  it('uses U+066B for the decimal point in Persian mode', () => {
    expect(formatNumber(1500.5, { decimals: 1, latin: false })).toBe('۱٬۵۰۰٫۵')
  })

  it('uses a plain dot for the decimal point in Latin mode', () => {
    expect(formatNumber(1500.5, { decimals: 1 })).toBe('1,500.5')
  })

  it('falls back to zero for garbage input rather than NaN', () => {
    expect(formatNumber('not a number')).toBe('0')
    expect(formatNumber('not a number', { latin: false })).toBe('۰')
  })

  it('rounds before splitting, so 1500.5 is not off by one', () => {
    // Splitting before rounding would take the integer part from 1500.5 and
    // render 1,501.5.
    expect(formatNumber(1500.5, { decimals: 1 })).toBe('1,500.5')
  })
})

describe('formatMoney', () => {
  it('renders a grouped amount in Latin digits with the currency unit', () => {
    expect(formatMoney(250000)).toBe(`250,000 ${CURRENCY_UNIT}`)
  })

  it('never shows two decimal places for whole Toman', () => {
    // The spec explicitly rejects `250000.00`.
    const text = formatMoney(250000)
    expect(text).not.toContain('.')
    expect(text).not.toContain('٫')
  })

  it('accepts the decimal string the API actually sends', () => {
    expect(formatMoney('1500000.00')).toBe(`1,500,000 ${CURRENCY_UNIT}`)
  })

  it('matches the Persian example when that mode is selected', () => {
    expect(formatMoney(250000, { latin: false })).toBe(`۲۵۰٬۰۰۰ ${CURRENCY_UNIT}`)
  })

  it('prefixes a plus sign when signed', () => {
    expect(formatMoney(1000, { signed: true })).toBe(`+1,000 ${CURRENCY_UNIT}`)
  })

  it('uses a real minus sign for negatives', () => {
    // U+2212 MINUS SIGN, not a hyphen — it aligns with digits in a column.
    expect(formatMoney(-1000)).toBe(`−1,000 ${CURRENCY_UNIT}`)
    expect(formatMoney(-1000)).toContain('−')
  })

  it('omits the unit on request', () => {
    expect(formatMoney(250000, { withUnit: false })).toBe('250,000')
  })

  it('treats null and undefined as zero instead of throwing', () => {
    expect(formatMoney(null)).toBe(`0 ${CURRENCY_UNIT}`)
    expect(formatMoney(undefined)).toBe(`0 ${CURRENCY_UNIT}`)
  })

  it('preserves exact seven-figure amounts with no rounding', () => {
    // 9,999,999 must not become 10,000,000.
    expect(formatMoney(9999999, { withUnit: false })).toBe('9,999,999')
    expect(formatMoney(9999999, { withUnit: false, latin: false })).toBe('۹٬۹۹۹٬۹۹۹')
  })
})

describe('formatMoneyCompact', () => {
  it('scales to میلیون', () => {
    expect(formatMoneyCompact(12500000)).toContain('میلیون')
    expect(formatMoneyCompact(12500000)).toContain('12.5')
  })

  it('scales to میلیارد', () => {
    expect(formatMoneyCompact(1200000000)).toContain('میلیارد')
  })

  it('keeps the scale word Persian in both modes', () => {
    // `12.5 میلیون` reads as Persian with Latin digits; `12.5 M` would
    // silently switch the interface language. Only the digits ever change.
    expect(formatMoneyCompact(12500000)).toContain('میلیون')
    expect(formatMoneyCompact(12500000, { latin: false })).toContain('میلیون')
    expect(formatMoneyCompact(1200000000)).toContain('میلیارد')
  })
})

describe('formatPercent', () => {
  it('uses an ASCII percent sign by default', () => {
    expect(formatPercent(65)).toBe('65%')
  })

  it('uses the Persian percent sign in Persian mode', () => {
    expect(formatPercent(65, 0, { latin: false })).toBe('۶۵٪')
  })

  it('respects the decimals argument', () => {
    expect(formatPercent(65.4, 1)).toBe('65.4%')
    expect(formatPercent(65.4, 1, { latin: false })).toBe('۶۵٫۴٪')
  })
})

describe('formatPercentChange', () => {
  it('always shows a sign for non-zero changes', () => {
    expect(formatPercentChange(12)).toBe('+12%')
    expect(formatPercentChange(-5)).toBe('−5%')
  })

  it('uses Persian digits only when that mode is on', () => {
    expect(formatPercentChange(12)).not.toMatch(/[۰-۹]/)
  })

  it('returns a dash when there is nothing to compare against', () => {
    expect(formatPercentChange(null)).toBe('—')
  })
})

describe('formatCount', () => {
  it('never shows decimals', () => {
    expect(formatCount(42)).toBe('42')
    expect(formatCount(0)).toBe('0')
  })
})

describe('formatDigits', () => {
  it('follows the product-wide numeral style', () => {
    expect(formatDigits(1234)).toBe(USE_PERSIAN_DIGITS ? '۱٬۲۳۴' : '1,234')
  })

  it('groups without decimals, whatever the input shape', () => {
    expect(formatDigits(999)).toBe('999')
    expect(formatDigits('1500000.00')).toBe('1,500,000')
  })
})

describe('formatYear', () => {
  it('never groups a year', () => {
    // A year is an identifier, not a quantity. Routing it through
    // `formatDigits` renders 1405 as `1,405`, which is nonsense on screen and
    // was a real regression when the Latin numeral switch landed.
    expect(formatYear(1405)).toBe('1405')
    expect(formatYear(1405)).not.toContain(',')
    expect(formatYear(1405)).not.toContain('\u066c')
  })

  it('follows the product numeral style', () => {
    expect(formatYear(1405)).toBe(USE_PERSIAN_DIGITS ? '۱۴۰۵' : '1405')
  })

  it('accepts a string year, as the API sends', () => {
    expect(formatYear('1405')).toBe('1405')
    expect(formatYear(' 1405 ')).toBe('1405')
  })

  it('leaves a four-digit year at four digits', () => {
    for (const year of [1300, 1405, 1499]) {
      expect(formatYear(year)).toHaveLength(4)
    }
  })
})

describe('latinize / latinizeDeep', () => {
  it('rewrites Persian digits in a server display string', () => {
    // This is what makes the API boundary the single place the numeral style
    // is applied: the backend builds `*_display` with Persian digits.
    expect(latinize('۲۵۰٬۰۰۰ تومان')).toBe('250,000 تومان')
  })

  it('leaves the currency word untouched', () => {
    expect(latinize('۱۴۰۵')).toBe('1405')
    expect(latinize('شهریور')).toBe('شهریور')
  })

  it('walks nested objects and arrays', () => {
    const payload = {
      amount_display: '۱٬۲۰۰٬۰۰۰ تومان',
      nested: { label: '۳ ماه', untouched: 'سلام' },
      items: [{ x: '۵' }, { y: 'no digits' }],
    }
    expect(latinizeDeep(payload)).toEqual({
      amount_display: '1,200,000 تومان',
      nested: { label: '3 ماه', untouched: 'سلام' },
      items: [{ x: '5' }, { y: 'no digits' }],
    })
  })

  it('returns the same reference when nothing needed changing', () => {
    // Preserving identity keeps TanStack Query's structural sharing working,
    // so an unchanged payload does not trigger a re-render.
    const payload = { a: 'سلام', b: ['plain', 'strings'] }
    expect(latinizeDeep(payload)).toBe(payload)
  })

  it('leaves non-plain objects alone rather than corrupting them', () => {
    // A shallow rebuild of a Date would turn it into `{}`.
    const date = new Date('2026-09-20T00:00:00Z')
    const payload = { when: date, label: '۲' }
    const out = latinizeDeep(payload)
    expect(out.when).toBe(date)
    expect(out.when instanceof Date).toBe(true)
    expect(out.label).toBe('2')
  })

  it('passes numbers and booleans through untouched', () => {
    expect(latinizeDeep(42)).toBe(42)
    expect(latinizeDeep(true)).toBe(true)
    expect(latinizeDeep(null)).toBeNull()
  })
})
