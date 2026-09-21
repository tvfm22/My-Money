/**
 * Numeral-policy regression tests.
 *
 * Every digit the interface shows is **Latin** (`0-9`) with an ASCII comma as
 * the thousands separator, whatever language the surrounding text is in.
 * Persian words, the Jalali calendar and the `تومان` unit are untouched — only
 * the glyphs for 0-9 differ. Money therefore reads `2,620,000 تومان`, never
 * `۲٬۶۲۰٬۰۰۰ تومان`.
 *
 * ## Why this file exists
 *
 * The switch to Latin digits is centralised in `utils/format.ts`, and
 * `services/client.ts` transliterates the server's `*_display` strings on the
 * way in. Two escape hatches still bypass both, and both have shipped:
 *
 *   1. A locale-dependent formatter — `count.toLocaleString('fa-IR')` — which
 *      asks the runtime for Persian digits regardless of product policy. Three
 *      such call sites survived the switch and were only found by reading a
 *      rendered dashboard.
 *   2. A Persian digit typed literally into JSX (`placeholder="۰"`), which no
 *      formatter ever sees.
 *
 * So the policy is checked at two layers:
 *
 *   * **Source** — no locale-dependent number formatting, and no Persian digit
 *     literals outside the two files that own the conversion tables.
 *   * **Rendered output** — every route is mounted and the whole document is
 *     swept for Persian/Arabic-Indic digits and the U+066C/U+066B separators.
 *     This is the assertion that would have caught the call sites above.
 *
 * A source scan is an unusual test, but the alternative is a per-component
 * assertion that only covers the components someone remembered to list — which
 * is exactly how three call sites slipped through.
 *
 * The sources are read through Vite's `import.meta.glob` rather than `node:fs`
 * so this file needs no Node type definitions and picks up the same file set
 * the bundler sees.
 */

import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { type ServerStub, installServerStub, renderApp } from './harness'
import { tokenStore } from '../services/client'

// ---------------------------------------------------------------------------
// Source scan
// ---------------------------------------------------------------------------

/** Every `.ts`/`.tsx` file under `src/`, as raw text, at build time. */
const SOURCES = import.meta.glob('/src/**/*.{ts,tsx}', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

/**
 * The only files allowed to contain Persian/Arabic-Indic digit literals.
 *
 * `format.ts` owns `PERSIAN_DIGITS`/`ARABIC_DIGITS` and the `'۰'` fallback;
 * `jalali.ts` owns the digit-by-digit date conversion. Both are the *tables*,
 * not call sites — everywhere else a Persian digit is a defect.
 */
const NUMERAL_TABLE_FILES = ['utils/format.ts', 'utils/jalali.ts']

/** Persian digits, Arabic-Indic digits, and the two Persian separators. */
const PERSIAN_NUMERAL_RE = /[\u06F0-\u06F9\u0660-\u0669\u066C\u066B]/g

/** Any `Number#toLocaleString` / `Date#toLocaleDateString` style call. */
const LOCALE_FORMATTER_RE = /\.toLocale(?:String|DateString|TimeString)\s*\(/g

/** `Intl` formatters, which default to the runtime locale's numbering system. */
const INTL_FORMATTER_RE = /\bnew\s+Intl\.(?:NumberFormat|DateTimeFormat|RelativeTimeFormat)\s*\(/g

/**
 * Application sources, keyed by their path relative to `src/`.
 *
 * The test directory is excluded: fixtures there are *supposed* to hold
 * Persian-digit strings, because transliterating them on the way in is the
 * behaviour under test.
 */
function sourceEntries(): Array<{ path: string; source: string }> {
  return Object.entries(SOURCES)
    .map(([file, source]) => ({ path: file.replace(/^\/src\//, ''), source }))
    .filter(({ path }) => !path.startsWith('test/'))
}

/**
 * Blank out comments while preserving every character offset.
 *
 * Comments are replaced with spaces rather than deleted, and newlines are kept,
 * so a match index still maps to the right source line. Without this, the
 * explanatory comments in `format.ts` — which quote `toLocaleString('en-US')`
 * and `۱٬۲۳۴` as counter-examples — would fail the scan they document.
 *
 * A small state machine is used rather than a regex because a `//` inside a
 * string literal is not a comment, and getting that wrong would hide a real
 * violation.
 */
function stripComments(source: string): string {
  const out = source.split('')
  let i = 0
  let state: 'code' | 'line' | 'block' | 'single' | 'double' | 'template' = 'code'

  const blank = (from: number, to: number) => {
    for (let k = from; k < to && k < out.length; k += 1) {
      if (out[k] !== '\n') out[k] = ' '
    }
  }

  while (i < source.length) {
    const ch = source[i]
    const next = source[i + 1]

    if (state === 'code') {
      if (ch === '/' && next === '/') {
        blank(i, i + 2)
        state = 'line'
        i += 2
        continue
      }
      if (ch === '/' && next === '*') {
        blank(i, i + 2)
        state = 'block'
        i += 2
        continue
      }
      if (ch === "'") state = 'single'
      else if (ch === '"') state = 'double'
      else if (ch === '`') state = 'template'
      i += 1
      continue
    }

    if (state === 'line') {
      if (ch === '\n') state = 'code'
      else blank(i, i + 1)
      i += 1
      continue
    }

    if (state === 'block') {
      if (ch === '*' && next === '/') {
        blank(i, i + 2)
        state = 'code'
        i += 2
        continue
      }
      blank(i, i + 1)
      i += 1
      continue
    }

    // Inside a string or template literal: skip escapes, close on the matching
    // quote. Content is kept — a Persian digit inside a string is a violation.
    if (ch === '\\') {
      i += 2
      continue
    }
    if (
      (state === 'single' && ch === "'") ||
      (state === 'double' && ch === '"') ||
      (state === 'template' && ch === '`')
    ) {
      state = 'code'
    }
    i += 1
  }

  return out.join('')
}

/** 1-based line number of an offset, for a readable failure message. */
function lineOf(source: string, index: number): number {
  let line = 1
  for (let k = 0; k < index; k += 1) if (source[k] === '\n') line += 1
  return line
}

/** Every match of `pattern` in `source`, as `path:line: snippet` strings. */
function findMatches(pattern: RegExp, source: string, path: string): string[] {
  const lines = source.split('\n')
  const hits: string[] = []
  pattern.lastIndex = 0

  for (let match = pattern.exec(source); match; match = pattern.exec(source)) {
    const line = lineOf(source, match.index)
    hits.push(`${path}:${line}: ${(lines[line - 1] ?? '').trim().slice(0, 90)}`)
  }

  return hits
}

describe('numeral policy — source', () => {
  it('never asks the runtime for a locale-specific number format', () => {
    const violations: string[] = []

    for (const { path, source } of sourceEntries()) {
      const code = stripComments(source)

      // `toLocaleString()` with no locale is worse than one with: it follows
      // the *browser's* locale, so the same build renders Persian digits for a
      // user in Tehran and Latin digits for a reviewer in CI.
      violations.push(...findMatches(LOCALE_FORMATTER_RE, code, path))
      violations.push(...findMatches(INTL_FORMATTER_RE, code, path))
    }

    expect(
      violations,
      'Locale-dependent number formatting bypasses the product numeral policy.\n' +
        'Use formatNumber / formatMoney / formatCount / formatPercent / formatJalali:\n  ' +
        violations.join('\n  '),
    ).toEqual([])
  })

  it('keeps Persian digit literals inside the conversion tables', () => {
    const violations: string[] = []

    for (const { path, source } of sourceEntries()) {
      if (NUMERAL_TABLE_FILES.includes(path)) continue
      violations.push(...findMatches(PERSIAN_NUMERAL_RE, stripComments(source), path))
    }

    expect(
      violations,
      `Persian digits and separators may only appear in ${NUMERAL_TABLE_FILES.join(', ')}.\n` +
        'Everywhere else they bypass every formatter. Use ZERO_PLACEHOLDER or formatDigits(...):\n  ' +
        violations.join('\n  '),
    ).toEqual([])
  })

  it('covers every source file it claims to check', () => {
    const files = sourceEntries().map(({ path }) => path)

    // A silently empty scan would make the two tests above pass while checking
    // nothing, so pin the shape of the file set.
    expect(files.length).toBeGreaterThan(40)
    expect(files).toContain('utils/format.ts')
    expect(files).toContain('features/dashboard/DashboardPage.tsx')
    // The test directory is excluded — it is allowed to hold Persian fixtures.
    expect(files.some((path) => path.startsWith('test/'))).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// Rendered output
// ---------------------------------------------------------------------------

let server: ServerStub

beforeEach(() => {
  server = installServerStub()
  tokenStore.set('test-access-token', 'test-refresh-token')
})

afterEach(() => {
  server.restore()
  tokenStore.clear()
})

/** Every route in `App.tsx`, including the debt detail screen. */
const ROUTES = [
  '/',
  '/transactions',
  '/budgets',
  '/budgets/performance',
  '/debts',
  '/debts/11',
  '/assets',
  '/reports',
  '/insights',
  '/settings',
]

/** Persian/Arabic-Indic digits and the two Persian separators, for text sweeps. */
const PERSIAN_IN_TEXT = /[\u06F0-\u06F9\u0660-\u0669\u066C\u066B]/g

describe('numeral policy — rendered screens', () => {
  for (const route of ROUTES) {
    it(`shows only Latin digits on ${route}`, async () => {
      renderApp([route])

      // Two waits, in this order, and both are load-bearing.
      //
      // `render()` returns before React has flushed its first commit, so an
      // immediate DOM read sees an almost empty document. A lone "no skeletons"
      // wait then passes *against that empty document* and the sweep asserts
      // nothing at all — it kept passing even with the client-side
      // transliteration interceptor switched off. Waiting for a shell landmark
      // first forces the commit; only after that does "no skeletons" actually
      // mean "the data arrived".
      await screen.findAllByLabelText('ناوبری اصلی')
      // The generous timeout absorbs the lazy-chunk import and the first
      // query round-trip when the whole suite runs in parallel workers; the
      // assertion itself still refuses to pass until the data has landed.
      await waitFor(
        () => {
          expect(document.querySelectorAll('[aria-busy="true"], .skeleton').length).toBe(0)
        },
        { timeout: 5000 },
      )

      const text = document.body.textContent ?? ''

      // Guard against re-introducing the vacuity above: a page still showing
      // placeholders has no figures to check.
      expect(text).not.toContain('در حال بارگذاری')
      expect(text.length).toBeGreaterThan(0)

      const offending = text.match(PERSIAN_IN_TEXT) ?? []

      expect(
        offending,
        `${route} rendered Persian numerals (${offending.join(' ')}). ` +
          'Every figure must go through utils/format.ts or be transliterated by the client interceptor.',
      ).toEqual([])
    })
  }

  it('formats a large amount with an ASCII comma, not U+066C', async () => {
    renderApp(['/'])

    // 12,500,000 spendable — the figure the dashboard leads with. The separator
    // matters as much as the digits: `12٬500٬000` is the worst of both worlds.
    const figure = await screen.findByText(/12,500,000/)
    expect(figure.textContent).not.toMatch(PERSIAN_IN_TEXT)
    expect(figure.textContent).toContain('12,500,000')
    expect(figure.textContent).toContain('تومان')
  })

  it('shows only Latin digits on every settings tab', async () => {
    const user = userEvent.setup()
    renderApp(['/settings'])

    await screen.findAllByLabelText('ناوبری اصلی')

    // Three of the four settings sections sit behind a tab, so a sweep of the
    // default view checks the profile form and nothing else. The accounts tab
    // is the one that renders server-provided balance strings — the most
    // numeral-dense part of the screen, and the one a route-level sweep misses.
    for (const tab of ['حساب کاربری', 'حساب‌های مالی', 'دسته‌بندی‌ها', 'امنیت']) {
      await user.click(screen.getByRole('button', { name: tab }))
      await waitFor(
        () => {
          expect(document.querySelectorAll('[aria-busy="true"], .skeleton').length).toBe(0)
        },
        { timeout: 5000 },
      )

      const text = document.body.textContent ?? ''
      expect(text, `tab «${tab}»`).not.toContain('در حال بارگذاری')
      expect(text.match(PERSIAN_IN_TEXT) ?? [], `tab «${tab}»`).toEqual([])

      if (tab === 'حساب‌های مالی') {
        // Prove the sweep had a balance to look at: 1,200,000 from the fixture,
        // which the server sends as «۱٬۲۰۰٬۰۰۰ تومان».
        expect(text).toContain('1,200,000')
      }
    }
  })
})
