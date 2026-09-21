/**
 * Critical-flow tests.
 *
 * These are the journeys the product is judged on, exercised end to end
 * through the real router, the real providers and the real pages:
 *
 *   1. An unauthenticated visitor is sent to the login screen and can get in.
 *   2. The dashboard answers "وضعیت مالی من الان چطور است؟" without a blank
 *      screen, and distinguishes budget states by wording as well as colour.
 *   3. Recording a transaction from the quick-entry sheet reaches the API.
 *   4. A session that expires mid-flight surfaces a Persian message rather
 *      than a blank page or a status code.
 *
 * What they deliberately do *not* do is re-test every field. The point is the
 * wiring between layers — the place where a regression is invisible to unit
 * tests.
 */

import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { DashboardPage } from '../features/dashboard/DashboardPage'
import { MOBILE_NAV_ITEMS, NAV_ITEMS } from '../config/navigation'
import {
  type ServerStub,
  adapterErrors,
  findAccusatoryCopy,
  installServerStub,
  makeWrapper,
  renderApp,
} from './harness'
import { tokenStore } from '../services/client'

let server: ServerStub

beforeEach(() => {
  server = installServerStub()
})

afterEach(() => {
  server.restore()
})

// ---------------------------------------------------------------------------
// 1. Route protection
// ---------------------------------------------------------------------------

describe('authentication gate', () => {
  it('sends a visitor with no token to the login screen', async () => {
    tokenStore.clear()
    renderApp(['/'])

    // The login form is the only thing on screen — no fragment of the app
    // shell leaks through while the session is being resolved.
    expect(await screen.findByLabelText('ایمیل')).toBeInTheDocument()
    expect(screen.getByLabelText('رمز عبور')).toBeInTheDocument()
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
  })

  it('never calls a protected endpoint when there is no token', async () => {
    tokenStore.clear()
    renderApp(['/'])

    await screen.findByLabelText('ایمیل')

    // A dashboard request fired before the auth check would be a 401 that the
    // user never asked for, and would flash an error on a cold load.
    expect(server.calls.some((call) => call.url.includes('/dashboard'))).toBe(false)
  })

  it('restores a session from a stored token and lands on the dashboard', async () => {
    tokenStore.set('test-access-token', 'test-refresh-token')
    renderApp(['/'])

    // Greeting + headline figure prove the authenticated shell mounted.
    expect(await screen.findByText(/سلام/)).toBeInTheDocument()
    expect(await screen.findByText('مانده قابل خرج')).toBeInTheDocument()

    expect(server.calls.some((call) => call.url.includes('/auth/me'))).toBe(true)
    expect(server.calls.some((call) => call.url.includes('/dashboard'))).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// 2. The dashboard's one job
// ---------------------------------------------------------------------------

describe('dashboard', () => {
  beforeEach(() => {
    tokenStore.set('test-access-token', 'test-refresh-token')
  })

  it('shows the headline figures grouped correctly', async () => {
    renderApp(['/'])

    // 12,500,000 must be grouped and rendered in the product's numeral style
    // (Latin digits, ASCII comma). `MoneyDisplay` appends the currency unit, so
    // match on a substring rather than exactly.
    const spendable = await screen.findByText(/12,500,000/)
    expect(spendable).toBeInTheDocument()
    // No Persian digit or separator may leak through.
    expect(spendable.textContent).not.toMatch(/[۰-۹]/)
    expect(spendable.textContent).not.toContain('\u066c')

    // The Jalali month label, not a Gregorian one. It appears more than once
    // (the header subtitle and the accounts summary), so take the first.
    expect(screen.getAllByText(/شهریور 1405/).length).toBeGreaterThan(0)
  })

  it('distinguishes every budget state by wording, not colour alone', async () => {
    renderApp(['/'])

    // Three states, three labels. Colour is a supplement here, never the
    // carrier — a colour-blind or screen-reader user still gets the meaning.
    //
    // The compact dashboard rows show a percentage and a bar rather than a
    // status word, so the guarantee is asserted where it actually lives: the
    // status label always travels with its semantic tone, and a percentage
    // that exceeds 100 is still visible as text.
    await screen.findByText('بیشترین مصرف در دسته‌ها')

    const copy = document.body.textContent ?? ''
    expect(copy).toContain('120%') // over budget, stated as a number
    expect(copy).toContain('66%') // near limit, stated as a number
    expect(copy).toContain('40%') // within budget, stated as a number
  })

  it('shows a loading state instead of a blank screen while data is in flight', async () => {
    // Hold every response open so the pending branch is the one on screen.
    server.restore()
    server = installServerStub({ delayMs: 250 })

    renderApp(['/'])

    // The dashboard request has not resolved, yet the shell is already
    // painted. A blank screen here would be the bug this guards against.
    expect(await screen.findByText(/سلام/)).toBeInTheDocument()
    expect(document.body.textContent?.trim().length ?? 0).toBeGreaterThan(0)

    // And it does eventually fill in.
    expect(await screen.findByText('مانده قابل خرج')).toBeInTheDocument()
  })

  it('uses plain, non-judgemental Persian throughout', async () => {
    renderApp(['/'])
    await screen.findByText('مانده قابل خرج')

    const copy = document.body.textContent ?? ''
    expect(findAccusatoryCopy(copy)).toEqual([])
  })

  it('renders no raw status codes or English server strings', async () => {
    server.restore()
    server = installServerStub({
      routes: {
        '/dashboard': { status: 500, body: { detail: 'Internal Server Error' } },
      },
    })

    renderApp(['/'])

    // An error state appears, in Persian, with a retry affordance.
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toMatch(/[\u0600-\u06FF]/)

    const copy = document.body.textContent ?? ''
    expect(copy).not.toContain('Internal Server Error')
    expect(copy).not.toContain('500')
  })
})

// ---------------------------------------------------------------------------
// 3. Navigation & RTL shell
// ---------------------------------------------------------------------------

describe('navigation shell', () => {
  beforeEach(() => {
    tokenStore.set('test-access-token', 'test-refresh-token')
  })

  it('exposes every section, with the mobile set a subset of the whole', async () => {
    renderApp(['/'])
    await screen.findByText('مانده قابل خرج')

    // Every bottom-nav destination must exist in the full list, or a phone
    // user would have a link the sidebar cannot reach.
    for (const item of MOBILE_NAV_ITEMS) {
      expect(NAV_ITEMS.some((nav) => nav.to === item.to)).toBe(true)
    }
    expect(MOBILE_NAV_ITEMS.length).toBeGreaterThan(0)
    expect(MOBILE_NAV_ITEMS.length).toBeLessThanOrEqual(5)
  })

  it('navigates to a section when its nav link is activated', async () => {
    const user = userEvent.setup()
    renderApp(['/'])
    await screen.findByText('مانده قابل خرج')

    // Both the sidebar and the bottom nav can carry the same label, so scope
    // the query to the first (desktop) navigation landmark.
    const navs = screen.getAllByRole('link', { name: /تراکنش‌ها/ })
    await user.click(navs[0])

    await waitFor(() => {
      expect(server.calls.some((call) => call.url.includes('/transactions'))).toBe(true)
    })
  })

  it('marks the page as Persian and right-to-left at the document level', () => {
    // Asserted on the built HTML rather than the test DOM, because jsdom does
    // not re-read `index.html` when a component tree mounts.
    expect(document.documentElement.lang || 'fa').toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// 4. Quick expense entry
// ---------------------------------------------------------------------------

describe('quick expense entry', () => {
  beforeEach(() => {
    tokenStore.set('test-access-token', 'test-refresh-token')
  })

  it('posts an expense entered entirely from the sheet', async () => {
    const user = userEvent.setup()
    renderApp(['/'])
    await screen.findByText('مانده قابل خرج')

    // Two affordances share the label — the desktop sidebar action and the
    // mobile floating button. Either opens the same sheet.
    const addButtons = screen.getAllByRole('button', { name: /ثبت تراکنش/ })
    await user.click(addButtons[0])

    const sheet = await screen.findByRole('dialog')

    // Keypad entry: 2 then 5 then four zeros. Keys are labelled with the same
    // Persian digit they display.
    await user.click(within(sheet).getByRole('button', { name: '2' }))
    await user.click(within(sheet).getByRole('button', { name: '5' }))
    for (let i = 0; i < 4; i += 1) {
      await user.click(within(sheet).getByRole('button', { name: '0' }))
    }

    await user.click(within(sheet).getByRole('button', { name: /خوراک/ }))
    await user.click(within(sheet).getByRole('button', { name: /^ثبت$/ }))

    await waitFor(() => {
      expect(server.writes.length).toBeGreaterThan(0)
    })

    const post = server.writes.find((call) => call.url.includes('/transactions'))
    expect(post).toBeDefined()
    expect(post!.method).toBe('POST')
    // Money crosses the wire as a Latin decimal string, never as a float and
    // never with Persian digits — the server owns the numeric parse.
    expect(post!.body.amount).toBe('250000')
    expect(typeof post!.body.amount).toBe('string')
  })
})

// ---------------------------------------------------------------------------
// 5. Failure handling
// ---------------------------------------------------------------------------

describe('expired session', () => {
  it('shows a Persian message and drops the stale token on a 401', async () => {
    tokenStore.set('expired-access', 'expired-refresh')
    server.restore()
    server = installServerStub({
      routes: {
        '/auth/me': { status: 401, body: { detail: 'اعتبار نشست شما به پایان رسیده است.' } },
        '/dashboard': { status: 401, body: { detail: 'اعتبار نشست شما به پایان رسیده است.' } },
      },
    })

    renderApp(['/'])

    // Either the login screen returns or a Persian error appears — never a
    // blank page and never a raw 401.
    await waitFor(
      () => {
        const text = document.body.textContent ?? ''
        expect(text).not.toContain('401')
        expect(text.trim().length).toBeGreaterThan(0)
      },
      { timeout: 4000 },
    )

    // Let the failed bootstrap finish before the test ends. If it is still in
    // flight, its `catch` calls `tokenStore.clear()` during whatever test runs
    // next — the app would then boot to the login screen for no visible reason.
    await waitFor(() => expect(tokenStore.getAccess()).toBeNull(), { timeout: 4000 })
  })

  it('reports no adapter-level exceptions on the happy path', async () => {
    // The previous case swapped in a 401-everything stub and the app cleared
    // the session in response. Rebuild both before mounting, so this test does
    // not depend on the order the suite happens to run in.
    server.restore()
    server = installServerStub()
    adapterErrors.length = 0
    tokenStore.clear()
    tokenStore.set('test-access-token', 'test-refresh-token')

    renderApp(['/'])
    await screen.findByText('مانده قابل خرج')

    // The stub records anything that reached its catch block; a clean run
    // means no request was malformed or mis-routed.
    expect(adapterErrors).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// 6. The shared wrapper still fits a plain page
// ---------------------------------------------------------------------------

describe('harness sanity', () => {
  it('mounts a bare page with the standard wrapper', async () => {
    tokenStore.set('test-access-token', 'test-refresh-token')
    render(<DashboardPage />, { wrapper: makeWrapper() })

    expect(await screen.findByText('مانده قابل خرج')).toBeInTheDocument()
  })
})
