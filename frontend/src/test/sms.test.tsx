/**
 * Render and interaction coverage for the bank-SMS import screens.
 *
 * The flow suite covers the dashboard; every other screen is covered the way
 * `pages.test.tsx` covers its pages: mount through the real provider stack,
 * stub the server at the axios-adapter level, and assert on observable text.
 *
 * The SMS screens add two write paths worth pinning down:
 *
 *   * staging (`POST /sms/parse/` is a read; `POST /sms/batches/` stores) —
 *     the distinction is the backend's whole safety story, so the tests
 *     assert which verb actually fired;
 *   * classification (`PATCH /sms/items/{id}/` carries the user's decisions).
 */

import { describe, expect, it, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'

import {
  SMS_BATCH_DETAIL,
  SMS_BATCHES_PAGE,
  SMS_ITEM_PENDING,
  SMS_REMINDER,
  SMS_RECONCILIATION,
  installServerStub,
  adapterErrors,
  makeWrapper,
} from './harness'
import { tokenStore } from '../services/client'

import { SmsImportPage } from '../features/sms/SmsImportPage'
import { SmsBatchReviewPage } from '../features/sms/SmsBatchReviewPage'

function renderPage(
  element: React.ReactElement,
  { path = '/', route = '/' } = {},
) {
  return render(
    <Routes>
      <Route path={path} element={element} />
    </Routes>,
    { wrapper: makeWrapper([route]) },
  )
}

function withToken(): void {
  tokenStore.set('test-access', 'test-refresh')
}

afterEach(() => {
  expect(adapterErrors, `stub adapter errors: ${adapterErrors.join(' | ')}`).toEqual([])
})

async function settle(): Promise<void> {
  await waitFor(() => {
    expect(document.querySelectorAll('[aria-busy="true"]').length).toBe(0)
  })
}

// ---------------------------------------------------------------------------
// SmsImportPage
// ---------------------------------------------------------------------------

describe('SmsImportPage', () => {
  it('renders the reminder banner, the paste form and the history list', async () => {
    installServerStub()
    withToken()

    const { container } = renderPage(<SmsImportPage />, { path: '/sms', route: '/sms' })

    await screen.findByRole('heading', { name: 'وارد کردن پیامک بانکی' })
    // The reminder banner shows the server-authored monthly message; digits
    // arrive Persian and render transliterated, so match on digits-free text.
    expect(await screen.findByText(/تمام شد؛ پیامک‌های بانکی آن را وارد کنید/)).toBeTruthy()
    await settle()

    // The history list renders the server's period label (digits transliterated).
    expect(container.textContent).toContain('مرداد 1405')
    expect(container.textContent).toContain('در انتظار بررسی')
  })

  it('previews a paste without staging anything', async () => {
    const stub = installServerStub({
      routes: {
        '/sms/parse': {
          body: {
            period: { year: 1405, month: 5, label: 'مرداد ۱۴۰۵' },
            summary: { total: 1, readable: 1, without_balance: 0, not_transaction: 0, low_confidence: 0 },
            messages: [
              {
                raw_text: 'بانک ملت: خرید کارت ... مبلغ ۲۵۰,۰۰۰ ریال',
                bank: 'mellat',
                bank_label: 'بانک ملت',
                sender: '',
                is_transaction: true,
                noise_kind: '',
                direction: 'expense',
                direction_pattern: 'card_purchase',
                amount: '25000.00',
                amount_unit: 'toman',
                amount_unit_assumed: false,
                balance_after: '1200000.00',
                balance_label: 'موجودی',
                occurred_on: '2026-08-20',
                date_source: 'message',
                card_last4: '1234',
                merchant: 'فروشگاه',
                description: 'خرید کارت',
                confidence: '0.92',
                field_confidence: {},
                warnings: [],
                fingerprint: 'fp-1',
              },
            ],
          },
        },
      },
    })
    withToken()
    const user = userEvent.setup()

    const { container } = renderPage(<SmsImportPage />, { path: '/sms', route: '/sms' })
    await settle()

    await user.type(
      screen.getByLabelText('پیامک‌ها'),
      'بانک ملت: خرید کارت ... مبلغ ۲۵۰,۰۰۰ ریال',
    )
    await user.click(screen.getByRole('button', { name: 'پیش‌نمایش' }))

    // The preview is a read (`POST /sms/parse/` writes nothing); staging is a
    // separate deliberate click that this test deliberately never makes.
    await waitFor(() => {
      const parseCall = stub.calls.find((call) => call.url.includes('/sms/parse'))
      expect(parseCall?.method).toBe('POST')
      expect(parseCall?.body.text).toContain('بانک ملت')
    })
    await screen.findByText(/پیش‌نمایش مرداد/)
    expect(container.textContent).toContain('بانک ملت')

    expect(stub.writes.filter((call) => call.url.includes('/sms/batches'))).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// SmsBatchReviewPage
// ---------------------------------------------------------------------------

describe('SmsBatchReviewPage', () => {
  function renderReview() {
    return renderPage(<SmsBatchReviewPage />, {
      path: '/sms/batches/:id',
      route: '/sms/batches/1',
    })
  }

  it('renders the batch, its items and the reconciliation figures', async () => {
    const { container } = renderReview()
    await screen.findByRole('heading', { name: /بررسی مرداد/ })
    await settle()

    // The pending expense shows its parsed amount; the noise message shows
    // its status instead of an amount.
    expect(container.textContent).toContain('25,000')
    expect(container.textContent).toContain('غیرتراکنشی')

    // Reconciliation: drift figures come from the server as Persian-digit
    // display strings and render transliterated.
    await screen.findByText('تطبیق موجودی')
    await waitFor(() => {
      expect(container.textContent).toContain('1,200,000')
    })
    expect(container.textContent).toContain('اختلاف با دفتر')
  })

  it('saves an item decision as a PATCH on the staged row', async () => {
    const stub = installServerStub()
    withToken()
    const user = userEvent.setup()

    const { container } = renderReview()
    await settle()
    expect(container.textContent).toContain('25,000')

    await user.selectOptions(
      screen.getByRole('combobox', { name: 'دسته‌بندی فروشگاه' }),
      '1',
    )
    await user.click(screen.getByRole('button', { name: 'ذخیره' }))

    await waitFor(() => {
      const patch = stub.writes.find((call) => call.url.includes('/sms/items/101'))
      expect(patch?.method).toBe('PATCH')
      expect(patch?.body.category).toBe(1)
    })
    await screen.findByText('ذخیره شد.')
  })

  it('skips a selected item through the bulk endpoint', async () => {
    const stub = installServerStub()
    withToken()
    const user = userEvent.setup()

    renderReview()
    await settle()

    await user.click(
      screen.getByRole('checkbox', { name: 'انتخاب قلم فروشگاه' }),
    )
    await user.click(screen.getByRole('button', { name: 'رد کردن انتخاب‌ها' }))

    await waitFor(() => {
      const bulk = stub.writes.find((call) => call.url.includes('/sms/items/bulk'))
      expect(bulk?.method).toBe('POST')
      expect(bulk?.body.item_ids).toEqual([SMS_ITEM_PENDING.id])
      expect(bulk?.body.status).toBe('skipped')
    })
  })

  it('commits the batch through the commit action and shows the result', async () => {
    const stub = installServerStub({
      routes: {
        '/sms/batches/1/commit': {
          body: {
            batch: SMS_BATCH_DETAIL,
            imported_count: 1,
            missing_category_count: 0,
            incomplete_count: 0,
            not_transaction_count: 1,
            transactions: [],
            message: '1 تراکنش ثبت شد.',
          },
        },
      },
    })
    withToken()
    const user = userEvent.setup()

    const { container } = renderReview()
    await settle()
    expect(container.textContent).toContain('مرداد 1405')

    await user.click(screen.getByRole('button', { name: /ثبت .* قلم در دفتر/ }))

    await waitFor(() => {
      const commitCall = stub.writes.find((call) => call.url.includes('/sms/batches/1/commit'))
      expect(commitCall?.method).toBe('POST')
    })
    // The server's sentence — what happened *and* what did not — is surfaced.
    expect(await screen.findByText('1 تراکنش ثبت شد.')).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// Reminder dismissal and history rendering
// ---------------------------------------------------------------------------

describe('SmsImportPage reminder', () => {
  it('dismisses the monthly prompt for the suggested period', async () => {
    const stub = installServerStub()
    withToken()
    const user = userEvent.setup()

    renderPage(<SmsImportPage />, { path: '/sms', route: '/sms' })
    await screen.findByText(/تمام شد؛ پیامک‌های بانکی آن را وارد کنید/)

    await user.click(screen.getByRole('button', { name: 'نمایش نده' }))

    await waitFor(() => {
      const dismissal = stub.writes.find((call) => call.url.includes('/sms/reminder'))
      expect(dismissal?.method).toBe('POST')
      expect(dismissal?.body.period_year).toBe(SMS_REMINDER.suggested_year)
      expect(dismissal?.body.period_month).toBe(SMS_REMINDER.suggested_month)
    })
  })

  it('renders the staged batch with its counts and review link', async () => {
    installServerStub({ routes: { '/sms/batches': { body: SMS_BATCHES_PAGE } } })
    withToken()

    const { container } = renderPage(<SmsImportPage />, { path: '/sms', route: '/sms' })
    await settle()

    expect(container.textContent).toContain('0 ثبت‌شده')
    expect(container.textContent).toContain('در انتظار بررسی')
    // The reconcile panel belongs to the review screen; asserting its absence
    // guards against the review page's panel leaking into the import page.
    expect(container.textContent).not.toContain('اختلاف با دفتر')
  })
})

describe('SmsBatchReviewPage reconciliation action', () => {
  it('describes the drift and offers to align the opening balance', async () => {
    const stub = installServerStub({
      routes: { '/sms/batches/1/reconcile': { body: SMS_RECONCILIATION } },
    })
    withToken()
    const user = userEvent.setup()

    const { container } = renderPage(<SmsBatchReviewPage />, {
      path: '/sms/batches/:id',
      route: '/sms/batches/1',
    })
    await settle()
    expect(container.textContent).toContain('1,200,000')

    await user.click(
      screen.getByRole('button', { name: 'هماهنگ‌سازی موجودی اولیه حساب' }),
    )
    await waitFor(() => {
      const apply = stub.writes.find((call) => call.url.includes('/reconcile/apply'))
      expect(apply?.method).toBe('POST')
    })
  })
})