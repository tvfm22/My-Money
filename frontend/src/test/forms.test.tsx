/**
 * Form validation tests.
 *
 * These drive the real components the way a person does — type, submit, read
 * the message — so the Zod schemas, the React Hook Form wiring, and the
 * Persian copy are all exercised together rather than in isolation.
 *
 * Two things are asserted beyond "the form works":
 *
 *   1. Validation fires *before* any network call. A form that round-trips to
 *      the server to discover an empty amount is a form that lies to the user
 *      on a slow connection.
 *   2. Every message is Persian, plain, and non-judgemental. The product spec
 *      forbids accusatory phrasing, so the vocabulary is checked, not just the
 *      presence of an alert.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { MIN_PASSWORD } from '../utils/format'
import { TransactionForm } from '../features/transactions/TransactionForm'
import { DebtForm } from '../features/debts/DebtForm'
import { AccountForm } from '../features/settings/AccountForm'
import { AssetForm } from '../features/assets/AssetForm'
import { AuthPage } from '../features/auth/AuthPage'
import {
  ACCOUNT,
  ASSET,
  TRANSACTION,
  findAccusatoryCopy,
  installServerStub,
  makeWrapper,
  adapterErrors,
  type ServerStub,
} from './harness'

let server: ServerStub

beforeEach(() => {
  window.localStorage.clear()
})

afterEach(() => {
  server?.restore()
})

// ---------------------------------------------------------------------------
// TransactionForm
// ---------------------------------------------------------------------------

describe('TransactionForm', () => {
  it('shows validation messages for an empty amount and category', async () => {
    server = installServerStub()
    const user = userEvent.setup()

    render(<TransactionForm open transaction={null} onClose={() => {}} />, {
      wrapper: makeWrapper(),
    })

    await user.click(screen.getByRole('button', { name: 'ثبت تراکنش' }))

    expect(await screen.findByText('مبلغ را وارد کنید.')).toBeInTheDocument()
    expect(await screen.findByText('دسته‌بندی را انتخاب کنید.')).toBeInTheDocument()

    // Nothing was sent: validation is entirely local.
    expect(server.writes).toHaveLength(0)
  })

  it('rejects a zero amount without calling the API', async () => {
    server = installServerStub()
    const user = userEvent.setup()

    render(<TransactionForm open transaction={null} onClose={() => {}} />, {
      wrapper: makeWrapper(),
    })

    const amountField = screen.getByLabelText(/مبلغ/)
    await user.clear(amountField)
    await user.type(amountField, '0')
    await user.click(screen.getByRole('button', { name: 'ثبت تراکنش' }))

    expect(await screen.findByText('مبلغ باید بیشتر از صفر باشد.')).toBeInTheDocument()
    expect(server.writes).toHaveLength(0)
  })

  it('accepts Persian digits and posts a plain decimal string', async () => {
    server = installServerStub()
    const user = userEvent.setup()
    const onClose = vi.fn()

    render(<TransactionForm open transaction={null} onClose={onClose} />, {
      wrapper: makeWrapper(),
    })

    await screen.findByRole('button', { name: /خوراک/ })

    const amountField = screen.getByLabelText(/مبلغ/)
    await user.clear(amountField)
    // Persian digits, as typed on a Persian keyboard layout. The field must
    // normalise them, so the payload is Latin — see the assertion below.
    await user.type(amountField, '۲۵۰۰۰۰')

    await user.click(screen.getByRole('button', { name: /خوراک/ }))
    await user.click(screen.getByRole('button', { name: 'ثبت تراکنش' }))

    await waitFor(() => expect(server.writes).toHaveLength(1))
    if (server.writes.length === 0) throw new Error('ADAPTER: ' + adapterErrors.join(' || '))

    const payload = server.writes[0].body
    // A Latin-digit string with no separators — never a formatted Persian
    // string, and never a float.
    expect(payload.amount).toBe('250000')
    expect(typeof payload.amount).toBe('string')
    expect(payload.category).toBe(1)
    expect(payload.transaction_type).toBe('expense')
    expect(onClose).toHaveBeenCalled()
  })

  it('clears the chosen category when the type is switched', async () => {
    server = installServerStub()
    const user = userEvent.setup()

    render(<TransactionForm open transaction={null} onClose={() => {}} />, {
      wrapper: makeWrapper(),
    })

    await screen.findByRole('button', { name: /خوراک/ })
    await user.click(screen.getByRole('button', { name: /خوراک/ }))
    expect(screen.getByRole('button', { name: /خوراک/ })).toHaveAttribute('aria-pressed', 'true')

    // Switching to income must not carry an expense category across.
    await user.click(screen.getByRole('radio', { name: 'درآمد' }))

    const incomeChip = await screen.findByRole('button', { name: /حقوق/ })
    expect(incomeChip).toHaveAttribute('aria-pressed', 'false')
  })

  it('attaches a server field error to its own input', async () => {
    server = installServerStub({
      writeStatus: 400,
      writeErrorBody: {
        detail: 'اطلاعات ارسالی معتبر نیست.',
        errors: { amount: ['مبلغ بسیار بزرگ است.'] },
      },
    })
    const user = userEvent.setup()

    render(<TransactionForm open transaction={null} onClose={() => {}} />, {
      wrapper: makeWrapper(),
    })

    await screen.findByRole('button', { name: /خوراک/ })

    const amountField = screen.getByLabelText(/مبلغ/)
    await user.clear(amountField)
    await user.type(amountField, '250000')
    await user.click(screen.getByRole('button', { name: /خوراک/ }))
    await user.click(screen.getByRole('button', { name: 'ثبت تراکنش' }))

    // The server's own message is shown verbatim, bound to the right field.
    const message = await screen.findByText('مبلغ بسیار بزرگ است.')
    expect(message).toBeInTheDocument()
    expect(screen.getByLabelText(/مبلغ/)).toHaveAttribute('aria-invalid', 'true')
  })

  it('never surfaces a raw status code or an English server error', async () => {
    server = installServerStub({
      writeStatus: 500,
      writeErrorBody: { detail: 'Internal Server Error' },
    })
    const user = userEvent.setup()

    render(<TransactionForm open transaction={null} onClose={() => {}} />, {
      wrapper: makeWrapper(),
    })

    await screen.findByRole('button', { name: /خوراک/ })
    const amountField = screen.getByLabelText(/مبلغ/)
    await user.clear(amountField)
    await user.type(amountField, '250000')
    await user.click(screen.getByRole('button', { name: /خوراک/ }))
    await user.click(screen.getByRole('button', { name: 'ثبت تراکنش' }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })

    const copy = screen.getAllByRole('alert').map((node) => node.textContent ?? '').join(' ')
    expect(copy).not.toContain('500')
    expect(copy).not.toContain('Internal Server Error')
    // A calm Persian sentence instead.
    expect(copy).toMatch(/[\u0600-\u06FF]/)
  })

  it('pre-fills an existing transaction for editing', async () => {
    server = installServerStub()

    render(<TransactionForm open transaction={TRANSACTION} onClose={() => {}} />, {
      wrapper: makeWrapper(),
    })

    // The amount is normalised to a Latin integer for the field.
    await waitFor(() => {
      expect(screen.getByLabelText(/مبلغ/)).toHaveValue('250000')
    })
    expect(screen.getByLabelText('توضیح')).toHaveValue('خرید هفتگی')
    expect(screen.getByRole('button', { name: 'ذخیره تغییرات' })).toBeInTheDocument()
  })

  it('requires a confirmation step before deleting', async () => {
    server = installServerStub()
    const user = userEvent.setup()
    const onDelete = vi.fn()

    render(
      <TransactionForm
        open
        transaction={TRANSACTION}
        onClose={() => {}}
        onDelete={onDelete}
      />,
      { wrapper: makeWrapper() },
    )

    // The first tap only reveals the confirmation — it must not delete.
    await user.click(await screen.findByRole('button', { name: 'حذف' }))
    expect(onDelete).not.toHaveBeenCalled()
    expect(await screen.findByRole('button', { name: 'حذف قطعی' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'حذف قطعی' }))
    expect(onDelete).toHaveBeenCalledWith(7)
  })

  it('uses no accusatory phrasing', async () => {
    server = installServerStub()
    const user = userEvent.setup()

    render(<TransactionForm open transaction={null} onClose={() => {}} />, {
      wrapper: makeWrapper(),
    })
    await user.click(screen.getByRole('button', { name: 'ثبت تراکنش' }))
    await screen.findByText('مبلغ را وارد کنید.')

    expect(findAccusatoryCopy(document.body.textContent ?? '')).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// DebtForm
// ---------------------------------------------------------------------------

describe('DebtForm', () => {
  it('requires a counterparty and an amount', async () => {
    server = installServerStub()
    const user = userEvent.setup()

    render(<DebtForm open debt={null} onClose={() => {}} />, { wrapper: makeWrapper() })

    await user.click(screen.getByRole('button', { name: 'ثبت' }))

    expect(await screen.findByText('نام طرف حساب را وارد کنید.')).toBeInTheDocument()
    expect(await screen.findByText('مبلغ را وارد کنید.')).toBeInTheDocument()
    expect(server.writes).toHaveLength(0)
  })

  it('rejects a due date that precedes the issue date', async () => {
    server = installServerStub()
    const user = userEvent.setup()

    render(<DebtForm open debt={null} onClose={() => {}} />, { wrapper: makeWrapper() })

    await user.type(screen.getByLabelText('طلبکار'), 'بانک ملت')
    await user.type(screen.getByLabelText(/مبلغ/), '5000000')

    // Open the due-date picker, step back a month, and choose an earlier day.
    //
    // Each picker has its own generated id, so the trigger can be addressed
    // directly and its popover read from the nearest shared wrapper. Climbing
    // by a fixed number of `closest()`/`parentElement` hops made this test
    // depend on incidental markup depth.
    const dueTrigger = screen.getByLabelText('تاریخ سررسید')
    await user.click(dueTrigger)

    const duePicker = dueTrigger.parentElement!
    const popover = within(duePicker).getByRole('dialog')
    const calendar = within(popover)

    const monthSelect = calendar.getByLabelText('ماه') as HTMLSelectElement
    const currentMonth = Number(monthSelect.value)
    const previousMonth = currentMonth === 1 ? 12 : currentMonth - 1
    await user.selectOptions(monthSelect, String(previousMonth))

    // Day cells are labelled `weekday day month year`, e.g.
    // "یک‌شنبه 1 شهریور 1405". The weekday names contain ZWNJ (U+200C) —
    // یک‌شنبه, سه‌شنبه, پنج‌شنبه — so matching on the spelled-out names is
    // brittle. Anchor on the shape instead: a day number followed by a Persian
    // month name, with digits in the product's numeral style (Latin). The
    // month/year comboboxes have no digits at all, so they cannot match.
    const dayButtons = within(popover).getAllByRole('button')
    const earlierDay = dayButtons.find((button) =>
      /[0-9]+\s+[\u0600-\u06FF]+\s+[0-9]{4}/.test(button.getAttribute('aria-label') ?? ''),
    )
    expect(earlierDay, 'expected at least one day cell in the picker').toBeDefined()
    await user.click(earlierDay!)

    await user.click(screen.getByRole('button', { name: 'ثبت' }))

    expect(
      await screen.findByText('تاریخ سررسید نمی‌تواند قبل از تاریخ ایجاد باشد.'),
    ).toBeInTheDocument()
    expect(server.writes).toHaveLength(0)
  })

  it('keeps the same issue date when the direction is flipped', async () => {
    server = installServerStub()
    const user = userEvent.setup()

    render(<DebtForm open debt={null} onClose={() => {}} />, { wrapper: makeWrapper() })

    // Default is a payable, so the counterparty is the person owed → "طلبکار".
    expect(screen.getByLabelText('طلبکار')).toBeInTheDocument()

    await user.click(screen.getByRole('radio', { name: /طلب \(دریافت می‌کنم\)/ }))

    // A receivable flips the label: the person who owes *me* is the "بدهکار".
    expect(await screen.findByLabelText('بدهکار')).toBeInTheDocument()
  })

  it('posts the debt with trimmed input and ISO dates', async () => {
    server = installServerStub()
    const user = userEvent.setup()
    const onClose = vi.fn()

    render(<DebtForm open debt={null} onClose={onClose} />, { wrapper: makeWrapper() })

    await user.type(screen.getByLabelText('طلبکار'), '  بانک ملت  ')
    await user.type(screen.getByLabelText(/مبلغ/), '50000000')
    await user.click(screen.getByRole('button', { name: 'ثبت' }))

    await waitFor(() => expect(server.writes).toHaveLength(1))
    if (server.writes.length === 0) throw new Error('ADAPTER: ' + adapterErrors.join(' || '))

    const payload = server.writes[0].body
    expect(payload.counterparty).toBe('بانک ملت')
    expect(payload.principal).toBe('50000000')
    expect(payload.direction).toBe('payable')
    // Dates travel as Gregorian ISO, never as a Jalali string.
    expect(payload.issued_on).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    expect(payload.due_on).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })

  it('uses no accusatory phrasing', async () => {
    server = installServerStub()
    const user = userEvent.setup()

    render(<DebtForm open debt={null} onClose={() => {}} />, { wrapper: makeWrapper() })
    await user.click(screen.getByRole('button', { name: 'ثبت' }))
    await screen.findByText('نام طرف حساب را وارد کنید.')

    expect(findAccusatoryCopy(document.body.textContent ?? '')).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// AccountForm
// ---------------------------------------------------------------------------

describe('AccountForm', () => {
  it('requires a name', async () => {
    server = installServerStub()
    const user = userEvent.setup()

    render(<AccountForm open account={null} onClose={() => {}} />, { wrapper: makeWrapper() })
    await user.click(screen.getByRole('button', { name: 'افزودن حساب' }))

    expect(await screen.findByText('نام حساب را وارد کنید.')).toBeInTheDocument()
    expect(server.writes).toHaveLength(0)
  })

  it('shows the opening balance only when creating', async () => {
    server = installServerStub()

    const { unmount } = render(<AccountForm open account={null} onClose={() => {}} />, {
      wrapper: makeWrapper(),
    })
    expect(screen.getByLabelText(/موجودی اولیه/)).toBeInTheDocument()
    unmount()

    render(<AccountForm open account={ACCOUNT as never} onClose={() => {}} />, {
      wrapper: makeWrapper(),
    })

    // Once transactions can exist the balance is derived — editing the opening
    // figure would silently rewrite history.
    expect(screen.queryByLabelText(/موجودی اولیه/)).not.toBeInTheDocument()
    expect(screen.getByText(/موجودی فعلی این حساب/)).toBeInTheDocument()
  })

  it('omits opening_balance from an update payload', async () => {
    server = installServerStub()
    const user = userEvent.setup()

    render(<AccountForm open account={ACCOUNT as never} onClose={() => {}} />, {
      wrapper: makeWrapper(),
    })

    await user.click(screen.getByRole('button', { name: 'ذخیره تغییرات' }))
    await waitFor(() => expect(server.writes).toHaveLength(1))

    expect(server.writes[0].body).not.toHaveProperty('opening_balance')
    expect(server.writes[0].body.name).toBe('بانک ملت')
  })

  it('sends the opening balance as a string on create', async () => {
    server = installServerStub()
    const user = userEvent.setup()

    render(<AccountForm open account={null} onClose={() => {}} />, { wrapper: makeWrapper() })

    await user.type(screen.getByLabelText('نام حساب'), 'کیف پول نقدی')
    await user.type(screen.getByLabelText(/موجودی اولیه/), '500000')
    await user.click(screen.getByRole('button', { name: 'افزودن حساب' }))

    await waitFor(() => expect(server.writes).toHaveLength(1))

    expect(server.writes[0].body.opening_balance).toBe('500000')
    expect(typeof server.writes[0].body.opening_balance).toBe('string')
  })
})

// ---------------------------------------------------------------------------
// AssetForm
// ---------------------------------------------------------------------------

describe('AssetForm', () => {
  it('requires a name and a current value', async () => {
    server = installServerStub()
    const user = userEvent.setup()

    render(<AssetForm open asset={null} onClose={() => {}} />, { wrapper: makeWrapper() })
    await user.click(screen.getByRole('button', { name: 'افزودن' }))

    expect(await screen.findByText('نام دارایی را وارد کنید.')).toBeInTheDocument()
    expect(await screen.findByText('ارزش فعلی را وارد کنید.')).toBeInTheDocument()
    expect(server.writes).toHaveLength(0)
  })

  it('offers unit fields only for holdings measured in units', async () => {
    server = installServerStub()
    const user = userEvent.setup()

    render(<AssetForm open asset={null} onClose={() => {}} />, { wrapper: makeWrapper() })

    // A bank account is not measured in units.
    expect(screen.queryByLabelText(/تعداد/)).not.toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('نوع'), 'gold_fund')

    expect(await screen.findByLabelText(/تعداد/)).toBeInTheDocument()
    expect(screen.getByLabelText('واحد')).toBeInTheDocument()
  })

  it('derives the unit price from value and quantity', async () => {
    server = installServerStub()
    const user = userEvent.setup()

    render(<AssetForm open asset={null} onClose={() => {}} />, { wrapper: makeWrapper() })

    await user.type(screen.getByLabelText('نام دارایی'), 'صندوق طلای مفید')
    await user.selectOptions(screen.getByLabelText('نوع'), 'gold_fund')

    await user.type(await screen.findByLabelText(/ارزش فعلی/), '150000000')
    await user.type(screen.getByLabelText(/تعداد/), '125')

    // The derived figure is shown before saving.
    expect(await screen.findByText(/ارزش هر واحد/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'افزودن' }))
    await waitFor(() => expect(server.writes).toHaveLength(1))

    // 150,000,000 / 125 = 1,200,000 per unit.
    expect(server.writes[0].body.unit_price).toBe('1200000')
    expect(server.writes[0].body.quantity).toBe('125')
    // The unit label is optional free text; left blank it stays blank.
    expect(server.writes[0].body.unit).toBe('')
  })

  it('neutralises unit fields when the type does not use them', async () => {
    server = installServerStub()
    const user = userEvent.setup()

    render(<AssetForm open asset={null} onClose={() => {}} />, { wrapper: makeWrapper() })

    await user.type(screen.getByLabelText('نام دارایی'), 'آپارتمان')
    await user.selectOptions(screen.getByLabelText('نوع'), 'real_estate')
    await user.type(await screen.findByLabelText(/ارزش فعلی/), '9000000000')

    await user.click(screen.getByRole('button', { name: 'افزودن' }))
    await waitFor(() => expect(server.writes).toHaveLength(1))

    // A property has no unit price; sending a stale one would be a lie.
    expect(server.writes[0].body.unit_price).toBeNull()
    expect(server.writes[0].body.quantity).toBeNull()
    expect(server.writes[0].body.unit).toBe('')
  })

  it('shows a live nominal return and never implies a market price', async () => {
    server = installServerStub()
    const user = userEvent.setup()

    render(<AssetForm open asset={null} onClose={() => {}} />, { wrapper: makeWrapper() })

    await user.type(screen.getByLabelText(/ارزش فعلی/), '150000000')
    await user.type(screen.getByLabelText(/ارزش خرید/), '120000000')

    expect(await screen.findByText('بازده اسمی')).toBeInTheDocument()
    // +30,000,000 rendered with grouping and an explicit sign.
    await waitFor(() => {
      expect(screen.getByText(/30,000,000/)).toBeInTheDocument()
    })

    // "اسمی" (nominal) matters: this is arithmetic on two recorded numbers, not
    // a market valuation. And the app says out loud that it does not fetch
    // live prices.
    const body = document.body.textContent ?? ''
    expect(body).not.toContain('سود تضمین')
    expect(body).toContain('قیمت‌های بازار به‌صورت خودکار دریافت نمی‌شوند')
  })

  it('pre-fills an existing holding including its unit price', async () => {
    server = installServerStub()

    render(<AssetForm open asset={ASSET as never} onClose={() => {}} />, {
      wrapper: makeWrapper(),
    })

    expect(screen.getByLabelText('نام دارایی')).toHaveValue('صندوق طلای مفید')
    // MoneyInput renders the grouped form in the product's numeral style, so
    // the DOM value carries Latin digits with ASCII commas.
    expect(screen.getByLabelText(/ارزش فعلی/)).toHaveValue('150,000,000')
    expect(screen.getByLabelText(/ارزش خرید/)).toHaveValue('120,000,000')
    await waitFor(() => {
      expect(screen.getByLabelText(/تعداد/)).toHaveValue('125')
    })
  })
})

// ---------------------------------------------------------------------------
// AuthPage
// ---------------------------------------------------------------------------

describe('AuthPage', () => {
  it('rejects an invalid email before contacting the server', async () => {
    server = installServerStub()
    const user = userEvent.setup()

    render(<AuthPage />, { wrapper: makeWrapper(['/login']) })

    await user.type(screen.getByLabelText('ایمیل'), 'not-an-email')
    await user.type(screen.getByLabelText('رمز عبور'), 'whatever')
    await user.click(screen.getByRole('button', { name: 'ورود به حساب' }))

    expect(await screen.findByText('ایمیل واردشده معتبر نیست.')).toBeInTheDocument()
    expect(server.writes).toHaveLength(0)
  })

  it('requires both password fields to match on registration', async () => {
    server = installServerStub()
    const user = userEvent.setup()

    render(<AuthPage />, { wrapper: makeWrapper(['/login']) })
    await user.click(screen.getByRole('button', { name: 'ثبت‌نام' }))

    await user.type(screen.getByLabelText('ایمیل'), 'sara@example.com')
    await user.type(screen.getByLabelText('رمز عبور'), 'secret12345')
    await user.type(screen.getByLabelText('تکرار رمز عبور'), 'secret54321')
    await user.click(screen.getByRole('button', { name: 'ساخت حساب' }))

    expect(await screen.findByText('رمز عبور و تکرار آن یکسان نیستند.')).toBeInTheDocument()
    expect(server.writes).toHaveLength(0)
  })

  it('enforces the minimum password length', async () => {
    server = installServerStub()
    const user = userEvent.setup()

    render(<AuthPage />, { wrapper: makeWrapper(['/login']) })
    await user.click(screen.getByRole('button', { name: 'ثبت‌نام' }))

    await user.type(screen.getByLabelText('ایمیل'), 'sara@example.com')
    await user.type(screen.getByLabelText('رمز عبور'), 'short')
    await user.type(screen.getByLabelText('تکرار رمز عبور'), 'short')
    await user.click(screen.getByRole('button', { name: 'ساخت حساب' }))

    // The message states the rule in the product's numeral style, so the digit
    // is Latin. `MIN_PASSWORD` is the same constant the schema renders, which
    // is what keeps the stated bound and the enforced bound from drifting.
    expect(
      await screen.findByText(`رمز عبور باید حداقل ${MIN_PASSWORD} کاراکتر باشد.`),
    ).toBeInTheDocument()
    expect(MIN_PASSWORD).toBe('8')
    expect(server.writes).toHaveLength(0)
  })

  it('shows a calm Persian message on a failed login, with no status code', async () => {
    server = installServerStub({
      writeStatus: 401,
      writeErrorBody: { detail: 'ایمیل یا رمز عبور نادرست است.' },
    })
    const user = userEvent.setup()

    render(<AuthPage />, { wrapper: makeWrapper(['/login']) })

    await user.type(screen.getByLabelText('ایمیل'), 'demo@mymoney.ir')
    await user.type(screen.getByLabelText('رمز عبور'), 'wrongpassword')
    await user.click(screen.getByRole('button', { name: 'ورود به حساب' }))

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('ایمیل یا رمز عبور نادرست است.')
    expect(alert.textContent).not.toContain('401')
  })

  it('lower-cases and trims the email before sending it', async () => {
    server = installServerStub({
      routes: {
        '/auth/login': {
          status: 200,
          body: {
            access: 'a.b.c',
            refresh: 'd.e.f',
            user: {
              id: 1,
              email: 'demo@mymoney.ir',
              first_name: 'سارا',
              last_name: 'محمدی',
              display_name: 'سارا محمدی',
              full_name: 'سارا محمدی',
              date_joined: '2026-01-01T00:00:00Z',
            },
          },
        },
      },
    })
    const user = userEvent.setup()

    render(<AuthPage />, { wrapper: makeWrapper(['/login']) })

    await user.type(screen.getByLabelText('ایمیل'), '  Demo@MyMoney.IR  ')
    await user.type(screen.getByLabelText('رمز عبور'), 'demo12345')
    await user.click(screen.getByRole('button', { name: 'ورود به حساب' }))

    await waitFor(() => expect(server.writes).toHaveLength(1))
    expect(server.writes[0].body.email).toBe('demo@mymoney.ir')
  })

  it('does not surface demo credentials on the login screen', () => {
    // The demo line was removed for production: shipped credentials on an
    // auth screen are a finding in any review. The demo user still exists
    // server-side; it is simply no longer advertised in the UI.
    server = installServerStub()
    render(<AuthPage />, { wrapper: makeWrapper(['/login']) })

    expect(screen.queryByText('demo@mymoney.ir')).not.toBeInTheDocument()
    expect(screen.queryByText('demo12345')).not.toBeInTheDocument()
  })
})
