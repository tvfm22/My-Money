import { describe, expect, it } from 'vitest'
import {
  addJalaliMonths,
  currentJalaliMonth,
  daysInJalaliMonth,
  formatJalali,
  formatRelativeDay,
  isJalaliLeapYear,
  isoToJalaliInput,
  jalaliMonthBounds,
  jalaliMonthGrid,
  jalaliToIso,
  jalaliWeekdayIndex,
  toGregorian,
  toJalali,
} from '../utils/jalali'

/**
 * The Jalali calendar is the app's primary calendar, so these tests are as
 * strict as the server-side ones. Anything that drifts here shows the user the
 * wrong day.
 */

describe('isJalaliLeapYear', () => {
  it('follows the 33-year cycle', () => {
    // Known leap years in the modern range.
    expect(isJalaliLeapYear(1399)).toBe(true)
    expect(isJalaliLeapYear(1403)).toBe(true)
    // 1405 is not a leap year, so اسفند has 29 days.
    expect(isJalaliLeapYear(1405)).toBe(false)
  })
})

describe('daysInJalaliMonth', () => {
  it('gives 31 days to the first six months', () => {
    for (let month = 1; month <= 6; month += 1) {
      expect(daysInJalaliMonth(1405, month)).toBe(31)
    }
  })

  it('gives 30 days to months 7 to 11', () => {
    for (let month = 7; month <= 11; month += 1) {
      expect(daysInJalaliMonth(1405, month)).toBe(30)
    }
  })

  it('gives اسفند 30 days in a leap year and 29 otherwise', () => {
    expect(daysInJalaliMonth(1399, 12)).toBe(30)
    expect(daysInJalaliMonth(1405, 12)).toBe(29)
  })
})

describe('toGregorian / toJalali round trip', () => {
  it('converts the epoch correctly', () => {
    const date = toGregorian(1, 1, 1)
    expect(date.getUTCFullYear()).toBe(622)
    expect(date.getUTCMonth() + 1).toBe(3)
    expect(date.getUTCDate()).toBe(21)
  })

  it('agrees with the server on a fixed date', () => {
    // The API test suite asserts 1405/06/29 == 2026-09-20 on both sides.
    expect(jalaliToIso(1405, 6, 29)).toBe('2026-09-20')
  })

  it('round-trips every day of a year without drift', () => {
    let iso = jalaliToIso(1404, 1, 1)
    const start = new Date(`${iso}T00:00:00Z`).getTime()

    for (let day = 0; day < 365; day += 1) {
      const current = new Date(start + day * 86_400_000)
      const isoDay = current.toISOString().slice(0, 10)
      const jalali = toJalali(isoDay)
      // Converting back must land on exactly the same day.
      expect(jalaliToIso(jalali.year, jalali.month, jalali.day)).toBe(isoDay)
    }

    iso = jalaliToIso(1404, 12, 29)
    expect(iso).toBeTruthy()
  })

  it('advances exactly one day across a year boundary', () => {
    const lastDay = jalaliToIso(1404, 12, 29)
    const firstDay = jalaliToIso(1405, 1, 1)

    const delta =
      (new Date(`${firstDay}T00:00:00Z`).getTime() -
        new Date(`${lastDay}T00:00:00Z`).getTime()) /
      86_400_000

    expect(delta).toBe(1)
  })
})

describe('jalaliWeekdayIndex', () => {
  it('starts the week on شنبه', () => {
    // 2026-09-20 is a Sunday; in the Jalali week that is index 1 (یکشنبه).
    expect(jalaliWeekdayIndex('2026-09-20')).toBe(1)
  })
})

describe('jalaliMonthGrid', () => {
  it('returns a whole number of weeks', () => {
    const grid = jalaliMonthGrid(1405, 6)
    expect(grid.length % 7).toBe(0)
  })

  it('contains every day of the requested month exactly once', () => {
    const grid = jalaliMonthGrid(1405, 6)
    const inMonth = grid.filter((cell) => cell.inMonth)
    expect(inMonth).toHaveLength(31)
    expect(inMonth[0].jalali.day).toBe(1)
    expect(inMonth[inMonth.length - 1].jalali.day).toBe(31)
  })

  it('pads with neighbouring months so the grid is rectangular', () => {
    const grid = jalaliMonthGrid(1405, 1)
    expect(grid.some((cell) => !cell.inMonth)).toBe(true)
  })

  it('places the first day in the column of its weekday', () => {
    const grid = jalaliMonthGrid(1405, 6)
    const firstIndex = grid.findIndex((cell) => cell.inMonth)
    const firstIso = jalaliToIso(1405, 6, 1)
    expect(firstIndex).toBe(jalaliWeekdayIndex(firstIso))
  })
})

describe('addJalaliMonths', () => {
  it('rolls December into January of the next year', () => {
    expect(addJalaliMonths(1405, 12, 1)).toEqual({ year: 1406, month: 1 })
  })

  it('rolls January back into December of the previous year', () => {
    expect(addJalaliMonths(1405, 1, -1)).toEqual({ year: 1404, month: 12 })
  })

  it('crosses multiple years', () => {
    expect(addJalaliMonths(1405, 3, 25)).toEqual({ year: 1407, month: 4 })
  })
})

describe('currentJalaliMonth', () => {
  it('returns a valid month', () => {
    const { year, month } = currentJalaliMonth()
    expect(month).toBeGreaterThanOrEqual(1)
    expect(month).toBeLessThanOrEqual(12)
    expect(year).toBeGreaterThan(1400)
  })
})

describe('jalaliMonthBounds', () => {
  it('spans the first to the last day of the month', () => {
    const bounds = jalaliMonthBounds(1405, 6)
    expect(bounds.from).toBe(jalaliToIso(1405, 6, 1))
    expect(bounds.to).toBe(jalaliToIso(1405, 6, 31))
  })

  it('handles a 29-day اسفند', () => {
    const bounds = jalaliMonthBounds(1405, 12)
    expect(bounds.to).toBe(jalaliToIso(1405, 12, 29))
  })
})

describe('formatJalali', () => {
  const iso = '2026-09-20' // ۱۴۰۵/۰۶/۲۹

  it('renders the numeric style', () => {
    expect(formatJalali(iso, 'numeric')).toBe('1405/06/29')
  })

  it('renders the short style', () => {
    // The month name is Persian; the day digit follows the product numeral
    // style, which is Latin.
    expect(formatJalali(iso, 'short')).toBe('29 شهریور')
  })

  it('renders the long style', () => {
    expect(formatJalali(iso, 'long')).toBe('29 شهریور 1405')
  })

  it('renders the full style with the weekday name', () => {
    const full = formatJalali(iso, 'full')
    expect(full).toContain('شهریور')
    expect(full).toContain('1405')
    // The weekday name is still Persian — that part is not a numeral.
    expect(full).toMatch(/[\u0600-\u06FF]/)
  })

  it('never groups the year', () => {
    // `1405` must not render as `1,405`. Dates are not quantities, so no
    // grouping separator may appear in any date style.
    for (const style of ['numeric', 'short', 'long', 'full', 'month'] as const) {
      const text = formatJalali(iso, style)
      expect(text, style).not.toContain(',')
      expect(text, style).not.toContain('\u066c')
    }
  })

  it('never emits a Persian digit under the default numeral style', () => {
    // A regression here would mean the numeral policy silently reverted.
    for (const style of ['numeric', 'short', 'long', 'full', 'month'] as const) {
      expect(formatJalali(iso, style), style).not.toMatch(/[۰-۹]/)
    }
  })

  it('renders a month label', () => {
    expect(formatJalali(iso, 'month')).toBe('شهریور 1405')
  })

  it('returns a dash for a missing date', () => {
    expect(formatJalali(null)).toBe('—')
    expect(formatJalali(undefined)).toBe('—')
  })
})

describe('formatRelativeDay', () => {
  it('names today and yesterday rather than showing a date', () => {
    const today = new Date()
    const todayIso = today.toISOString().slice(0, 10)
    const yesterday = new Date(today.getTime() - 86_400_000).toISOString().slice(0, 10)

    expect(formatRelativeDay(todayIso)).toBe('امروز')
    expect(formatRelativeDay(yesterday)).toBe('دیروز')
  })

  it('falls back to a Jalali date for older entries', () => {
    expect(formatRelativeDay('2026-01-15')).toContain('1404')
  })
})

describe('isoToJalaliInput', () => {
  it('produces the slash-separated form the API accepts', () => {
    // Latin digits on purpose: this feeds a form field, and the API's
    // JalaliDateField accepts either. Rendering is done by formatJalali.
    expect(isoToJalaliInput('2026-09-20')).toBe('1405/06/29')
  })

  it('handles an empty value', () => {
    expect(isoToJalaliInput('')).toBe('')
  })
})
