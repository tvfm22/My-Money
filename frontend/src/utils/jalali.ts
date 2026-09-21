/**
 * Jalali (Solar Hijri) calendar utilities for the client.
 *
 * The **server is the source of truth** for date conversion and sends every
 * date pre-formatted (`date_display`, `jalali_date`, `due_on_display`, ...).
 * The UI renders those strings.
 *
 * This module exists for the cases where the client genuinely needs to reason
 * about the calendar rather than just display it:
 *
 *   * the Jalali date picker, which has to lay out a month grid;
 *   * "this month / last month" quick filters, which need month boundaries
 *     before any data is fetched;
 *   * grouping a list of transactions by day heading.
 *
 * The conversion is the same 33-year-cycle arithmetic used on the server, and
 * it is pinned by unit tests against the same reference dates so the two
 * implementations cannot silently diverge.
 */

import { USE_PERSIAN_DIGITS } from './format'

/** Persian month names, indexed 0-11 (Farvardin … Esfand). */
export const JALALI_MONTHS = [
  'فروردین',
  'اردیبهشت',
  'خرداد',
  'تیر',
  'مرداد',
  'شهریور',
  'مهر',
  'آبان',
  'آذر',
  'دی',
  'بهمن',
  'اسفند',
] as const

/** Saturday-first weekday names, indexed 0-6. The Persian week starts Saturday. */
export const JALALI_WEEKDAYS = [
  'شنبه',
  'یک‌شنبه',
  'دوشنبه',
  'سه‌شنبه',
  'چهارشنبه',
  'پنج‌شنبه',
  'جمعه',
] as const

/** Single-letter weekday initials for the picker's header row. */
export const JALALI_WEEKDAYS_SHORT = ['ش', 'ی', 'د', 'س', 'چ', 'پ', 'ج'] as const

/**
 * JDN of 1/1/1 Jalali, and the matching proleptic-Gregorian date.
 * Both directions are anchored to this single pair, which is what makes them
 * exact inverses. Mirrors `apps/core/jalali.py`.
 */
const GREGORIAN_JALALI_EPOCH: [number, number, number] = [622, 3, 21]

export interface JalaliDate {
  year: number
  month: number // 1-12
  day: number // 1-31
}

// ---------------------------------------------------------------------------
// Julian Day Number helpers
// ---------------------------------------------------------------------------

/** Convert a proleptic Gregorian date to a Julian Day Number. */
function gregorianToJdn(year: number, month: number, day: number): number {
  const a = Math.floor((14 - month) / 12)
  const y = year + 4800 - a
  const m = month + 12 * a - 3
  return (
    day +
    Math.floor((153 * m + 2) / 5) +
    365 * y +
    Math.floor(y / 4) -
    Math.floor(y / 100) +
    Math.floor(y / 400) -
    32045
  )
}

/** Convert a Julian Day Number back to a proleptic Gregorian date. */
function jdnToGregorian(jdn: number): [number, number, number] {
  const a = jdn + 32044
  const b = Math.floor((4 * a + 3) / 146097)
  const c = a - Math.floor((146097 * b) / 4)
  const d = Math.floor((4 * c + 3) / 1461)
  const e = c - Math.floor((1461 * d) / 4)
  const m = Math.floor((5 * e + 2) / 153)
  const day = e - Math.floor((153 * m + 2) / 5) + 1
  const month = m + 3 - 12 * Math.floor(m / 10)
  const year = 100 * b + d - 4800 + Math.floor(m / 10)
  return [year, month, day]
}

const EPOCH_JDN = gregorianToJdn(...GREGORIAN_JALALI_EPOCH)

// ---------------------------------------------------------------------------
// Jalali arithmetic
// ---------------------------------------------------------------------------

/**
 * Is a Jalali year a leap year (366 days)?
 *
 * The Jalali leap rule is a 33-year cycle: year Y is leap when the 33-year
 * remainder is 1.
 */
export function isJalaliLeapYear(jalaliYear: number): boolean {
  return ((jalaliYear + 12) % 33) % 4 === 1
}

/** Number of days in a Jalali month. Months 1-6 have 31, 7-11 have 30, and
 *  Esfand has 29 or 30 depending on the leap year. */
export function daysInJalaliMonth(jalaliYear: number, jalaliMonth: number): number {
  if (jalaliMonth <= 6) return 31
  if (jalaliMonth <= 11) return 30
  return isJalaliLeapYear(jalaliYear) ? 30 : 29
}

/** Convert a Jalali date to a Julian Day Number. */
export function jalaliToJdn(year: number, month: number, day: number): number {
  let days = -1
  const yearsBefore = year - 1
  const cycle = Math.floor(yearsBefore / 33)
  const remainderYears = yearsBefore % 33

  days += cycle * 12053
  for (let i = 1; i <= remainderYears; i += 1) {
    days += isJalaliLeapYear(i) ? 366 : 365
  }
  for (let m = 1; m < month; m += 1) {
    days += daysInJalaliMonth(year, m)
  }
  days += day

  return EPOCH_JDN + days
}

/** Convert a Julian Day Number to a Jalali date. */
export function jdnToJalali(jdn: number): JalaliDate {
  const days = jdn - EPOCH_JDN + 1
  const cycle = Math.floor((days - 1) / 12053)
  let year = 1 + 33 * cycle
  let remainder = (days - 1) % 12053

  for (;;) {
    const yearLength = isJalaliLeapYear(year) ? 366 : 365
    if (remainder < yearLength) break
    remainder -= yearLength
    year += 1
  }

  let month: number
  let day: number
  if (remainder < 186) {
    month = Math.floor(remainder / 31) + 1
    day = (remainder % 31) + 1
  } else {
    remainder -= 186
    month = Math.floor(remainder / 30) + 7
    day = (remainder % 30) + 1
  }

  return { year, month, day }
}

// ---------------------------------------------------------------------------
// Conversion between calendars
// ---------------------------------------------------------------------------

/** Parse an ISO `YYYY-MM-DD` string into a Gregorian date. Returns null if invalid. */
export function parseIsoDate(iso: string | null | undefined): Date | null {
  if (!iso) return null
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso.trim())
  if (!match) return null
  const [, y, m, d] = match
  // Construct in UTC to avoid the local timezone shifting the calendar day.
  const date = new Date(Date.UTC(Number(y), Number(m) - 1, Number(d)))
  return Number.isNaN(date.getTime()) ? null : date
}

/** Convert a Gregorian `Date` (or ISO string) to a Jalali date. */
export function toJalali(value: Date | string): JalaliDate {
  const date = typeof value === 'string' ? parseIsoDate(value) : value
  if (!date) return { year: 1400, month: 1, day: 1 }
  const jdn = gregorianToJdn(
    date.getUTCFullYear(),
    date.getUTCMonth() + 1,
    date.getUTCDate(),
  )
  return jdnToJalali(jdn)
}

/** Convert a Jalali date to a Gregorian `Date` at UTC midnight. */
export function toGregorian(year: number, month: number, day: number): Date {
  const [gy, gm, gd] = jdnToGregorian(jalaliToJdn(year, month, day))
  return new Date(Date.UTC(gy, gm - 1, gd))
}

/** Convert a Jalali date to an ISO `YYYY-MM-DD` string. */
export function jalaliToIso(year: number, month: number, day: number): string {
  const [gy, gm, gd] = jdnToGregorian(jalaliToJdn(year, month, day))
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${gy}-${pad(gm)}-${pad(gd)}`
}

/** Convert an ISO date string to a Jalali `YYYY/MM/DD` input value. */
export function isoToJalaliInput(iso: string | null | undefined): string {
  if (!iso) return ''
  const { year, month, day } = toJalali(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${year}/${pad(month)}/${pad(day)}`
}

/** The Jalali month containing today, computed locally. */
export function currentJalaliMonth(): { year: number; month: number } {
  const now = new Date()
  const { year, month } = toJalali(now)
  return { year, month }
}

/**
 * First and last Gregorian day of a Jalali month, as ISO strings.
 * Used to build `date_from` / `date_to` filters without a round trip.
 */
export function jalaliMonthBounds(
  year: number,
  month: number,
): { from: string; to: string } {
  return {
    from: jalaliToIso(year, month, 1),
    to: jalaliToIso(year, month, daysInJalaliMonth(year, month)),
  }
}

/** Shift a Jalali (year, month) pair by a number of months. */
export function addJalaliMonths(
  year: number,
  month: number,
  delta: number,
): { year: number; month: number } {
  const total = (year * 12 + (month - 1)) + delta
  return { year: Math.floor(total / 12), month: (total % 12) + 1 }
}

/**
 * Index of a Gregorian day within the Persian week, Saturday = 0.
 *
 * JavaScript's `getUTCDay()` gives Sunday = 0, so shift by one and wrap.
 */
export function jalaliWeekdayIndex(value: Date | string): number {
  const date = typeof value === 'string' ? parseIsoDate(value) : value
  if (!date) return 0
  return (date.getUTCDay() + 1) % 7
}

/**
 * The month grid for the date picker: six weeks of Jalali days, padded with
 * the neighbouring months' days so the grid is always the same height.
 */
export function jalaliMonthGrid(
  year: number,
  month: number,
): Array<{ jalali: JalaliDate; iso: string; inMonth: boolean }> {
  const firstIso = jalaliToIso(year, month, 1)
  const firstWeekday = jalaliWeekdayIndex(firstIso)

  const cells: Array<{ jalali: JalaliDate; iso: string; inMonth: boolean }> = []

  // Leading days from the previous month.
  const previous = addJalaliMonths(year, month, -1)
  const previousDays = daysInJalaliMonth(previous.year, previous.month)
  for (let i = firstWeekday - 1; i >= 0; i -= 1) {
    const day = previousDays - i
    const iso = jalaliToIso(previous.year, previous.month, day)
    cells.push({
      jalali: { year: previous.year, month: previous.month, day },
      iso,
      inMonth: false,
    })
  }

  // The month itself.
  const total = daysInJalaliMonth(year, month)
  for (let day = 1; day <= total; day += 1) {
    cells.push({ jalali: { year, month, day }, iso: jalaliToIso(year, month, day), inMonth: true })
  }

  // Trailing days to fill the final week.
  const next = addJalaliMonths(year, month, 1)
  let day = 1
  while (cells.length % 7 !== 0) {
    const iso = jalaliToIso(next.year, next.month, day)
    cells.push({
      jalali: { year: next.year, month: next.month, day },
      iso,
      inMonth: false,
    })
    day += 1
  }

  return cells
}

// ---------------------------------------------------------------------------
// Display formatting (local fallbacks — prefer the server's strings)
// ---------------------------------------------------------------------------

/**
 * Format an ISO date as Jalali.
 *
 * Styles:
 *   numeric -> ۱۴۰۵/۰۶/۲۹
 *   short   -> ۲۹ شهریور
 *   long    -> ۲۹ شهریور ۱۴۰۵
 *   full    -> شنبه ۲۹ شهریور ۱۴۰۵
 *   month   -> شهریور ۱۴۰۵
 */
export function formatJalali(
  value: Date | string | null | undefined,
  style: 'numeric' | 'short' | 'long' | 'full' | 'month' = 'numeric',
): string {
  if (!value) return '—'
  const jalali = toJalali(value)
  const monthName = JALALI_MONTHS[jalali.month - 1]
  const pad = (n: number) => String(n).padStart(2, '0')

  switch (style) {
    case 'numeric':
      return toPersianDigitsLocal(`${jalali.year}/${pad(jalali.month)}/${pad(jalali.day)}`)
    case 'short':
      return toPersianDigitsLocal(`${jalali.day} ${monthName}`)
    case 'month':
      return toPersianDigitsLocal(`${monthName} ${jalali.year}`)
    case 'long':
      return toPersianDigitsLocal(`${jalali.day} ${monthName} ${jalali.year}`)
    case 'full': {
      const weekday = JALALI_WEEKDAYS[jalaliWeekdayIndex(typeof value === 'string' ? value : value)]
      return toPersianDigitsLocal(`${weekday} ${jalali.day} ${monthName} ${jalali.year}`)
    }
    default:
      return '—'
  }
}

/**
 * A short Jalali label for a date relative to today: 'امروز', 'دیروز', or a
 * Jalali date. Used as list headings.
 */
export function formatRelativeDay(iso: string): string {
  const date = parseIsoDate(iso)
  if (!date) return '—'

  const today = new Date()
  const todayUtc = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())
  const diffDays = Math.round((date.getTime() - todayUtc) / 86_400_000)

  if (diffDays === 0) return 'امروز'
  if (diffDays === -1) return 'دیروز'
  if (diffDays === 1) return 'فردا'
  return formatJalali(iso, 'long')
}

/** Local digit conversion, driven by the product-wide numeral style.
 *
 *  Kept private so `format.ts` stays the one public entry point for number
 *  formatting. Dates are formatted here rather than through `formatNumber`
 *  or `formatDigits` because a date is not a quantity: it must never be
 *  grouped or rounded. Passing a year through `formatDigits` would render
 *  `1405` as `1,405`, which is why dates convert digit-by-digit instead. */
function toPersianDigitsLocal(value: string | number): string {
  const text = String(value)
  return USE_PERSIAN_DIGITS
    ? text.replace(/[0-9]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[Number(d)])
    : text
}
