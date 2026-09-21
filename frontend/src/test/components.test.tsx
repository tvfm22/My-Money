import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ProgressBar } from '../components/ui/ProgressBar'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import { MoneyDisplay } from '../components/common/MoneyDisplay'
import { BudgetProgress } from '../components/common/BudgetProgress'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { JalaliDatePicker } from '../components/ui/JalaliDatePicker'
import type { BudgetCategoryAnalysis } from '../types'
import { categoryAnalysis } from './harness'

// ---------------------------------------------------------------------------

/**
 * A complete analysed category, built through the harness factory.
 *
 * This used to be a second hand-written literal, and the two copies drifted —
 * it declared `pace`/`pace_label` (which the server never sends) and omitted
 * `elapsed_percent`, `pace_delta` and the projection fields. Delegating to the
 * one factory means there is a single definition of the shape, and every field
 * is present and correctly named by construction.
 */
function makeAnalysis(overrides: Partial<BudgetCategoryAnalysis> = {}): BudgetCategoryAnalysis {
  return {
    ...categoryAnalysis({
      category_id: 1,
      category_name: 'خوراک',
      category_icon: 'utensils',
      category_color: '#12a150',
      is_essential: true,
      budgeted: '10000000.00',
      spent: '4000000.00',
      status: 'safe',
      status_label: 'در محدوده بودجه',
      pace_state: 'behind',
      message: 'وضعیت مناسب — مصرف شما از سرعت گذر ماه کمتر است.',
    }),
    ...overrides,
  }
}

// ---------------------------------------------------------------------------

describe('MoneyDisplay', () => {
  it('renders grouped Latin digits with the currency unit', () => {
    // The product renders numerals in Latin; the unit word stays Persian.
    render(<MoneyDisplay value="2500000.00" />)
    expect(screen.getByText(/2,500,000 تومان/)).toBeInTheDocument()
  })

  it('never renders a Persian digit or separator', () => {
    const { container } = render(<MoneyDisplay value="2500000.00" />)
    expect(container.textContent).not.toMatch(/[۰-۹]/)
    // U+066C would mean the numeral policy had silently reverted.
    expect(container.textContent).not.toContain('\u066c')
  })

  it('shows a plus sign only when signed is set', () => {
    const { rerender } = render(<MoneyDisplay value="1000" />)
    expect(screen.getByText(/1,000/).textContent).not.toContain('+')

    rerender(<MoneyDisplay value="1000" signed />)
    expect(screen.getByText(/1,000/).textContent).toContain('+')
  })

  it('colours a positive amount green when coloured', () => {
    const { container } = render(<MoneyDisplay value="1000" coloured />)
    expect(container.querySelector('.text-positive-600')).not.toBeNull()
  })

  it('colours a negative amount red', () => {
    const { container } = render(<MoneyDisplay value="-1000" coloured signed />)
    expect(container.querySelector('.text-critical-600')).not.toBeNull()
  })

  it('inverts the colour for a value where up is bad', () => {
    // A growing debt is negative news, so the colour must flip.
    const { container } = render(<MoneyDisplay value="1000" coloured invertColour />)
    expect(container.querySelector('.text-critical-600')).not.toBeNull()
  })

  it('renders zero for missing values instead of crashing', () => {
    render(<MoneyDisplay value={null} />)
    expect(screen.getByText(/0 تومان/)).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------

describe('ProgressBar', () => {
  it('exposes the value to assistive technology', () => {
    render(<ProgressBar value={65} label="میزان مصرف بودجه" />)
    const bar = screen.getByRole('progressbar')
    expect(bar).toHaveAttribute('aria-valuenow', '65')
    expect(bar).toHaveAttribute('aria-label', 'میزان مصرف بودجه')
  })

  it('clamps an over-budget value at 100 for the unclamped attribute', () => {
    render(<ProgressBar value={137} label="مصرف" />)
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '100')
  })

  it('renders the pace marker when given', () => {
    const { container } = render(
      <ProgressBar value={40} label="مصرف" markerPercent={60} />,
    )
    // Track fill, marker, and nothing else.
    expect(container.querySelectorAll('div').length).toBeGreaterThanOrEqual(3)
  })

  it('adds an overflow affordance beyond 100%', () => {
    const { container } = render(<ProgressBar value={120} label="مصرف" />)
    expect(container.querySelector('.bg-critical-700')).not.toBeNull()
  })
})

// ---------------------------------------------------------------------------

describe('Badge', () => {
  it('always carries a text label, never colour alone', () => {
    render(<Badge variant="caution">نزدیک سقف</Badge>)
    expect(screen.getByText('نزدیک سقف')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------

describe('Button', () => {
  it('shows a busy state and blocks a double submit while loading', async () => {
    const onClick = vi.fn()
    render(
      <Button isLoading onClick={onClick}>
        ثبت
      </Button>,
    )

    const button = screen.getByRole('button')
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('aria-busy', 'true')

    await userEvent.click(button)
    expect(onClick).not.toHaveBeenCalled()
  })

  it('fires its handler normally', async () => {
    const onClick = vi.fn()
    render(<Button onClick={onClick}>ثبت</Button>)

    await userEvent.click(screen.getByRole('button'))
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('centres the label of a full-width button', () => {
    // The base is `inline-flex`, so without `justify-center` a `fullWidth`
    // button packs its label against the start edge — which in this RTL layout
    // is the right edge. The login and register submits were both showing
    // «ورود به حساب» hard right instead of centred.
    //
    // jsdom does not resolve Tailwind, so the computed style is not available;
    // asserting the utility is present is the closest check that still fails if
    // someone drops it again.
    render(<Button fullWidth>ورود به حساب</Button>)
    expect(screen.getByRole('button').className).toContain('justify-center')
  })

  it('centres the label of every size', () => {
    // The `icon` size used to be the only one carrying `justify-center`, which
    // is what let the gap go unnoticed.
    for (const size of ['sm', 'md', 'lg'] as const) {
      const { unmount } = render(<Button size={size}>ثبت</Button>)
      expect(screen.getByRole('button').className, size).toContain('justify-center')
      unmount()
    }
  })
})

// ---------------------------------------------------------------------------

describe('Input', () => {
  it('associates its label with the control', () => {
    render(<Input label="مبلغ" name="amount" />)
    expect(screen.getByLabelText('مبلغ')).toBeInTheDocument()
  })

  it('marks the field invalid and announces the error', () => {
    render(<Input label="مبلغ" name="amount" error="مبلغ را وارد کنید." />)
    const input = screen.getByLabelText('مبلغ')
    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByRole('alert')).toHaveTextContent('مبلغ را وارد کنید.')
  })

  it('links the error through aria-describedby', () => {
    render(<Input label="مبلغ" name="amount" error="خطا" />)
    const input = screen.getByLabelText('مبلغ')
    const describedBy = input.getAttribute('aria-describedby')
    expect(describedBy).toBeTruthy()
    expect(document.getElementById(describedBy!)).toHaveTextContent('خطا')
  })
})

// ---------------------------------------------------------------------------

describe('EmptyState', () => {
  it('offers a way forward, not just a message', () => {
    render(
      <EmptyState
        title="هنوز تراکنشی ثبت نکرده‌اید"
        description="اولین تراکنش خود را ثبت کنید."
        action={<button type="button">ثبت تراکنش</button>}
      />,
    )

    expect(screen.getByText('هنوز تراکنشی ثبت نکرده‌اید')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'ثبت تراکنش' })).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------

describe('ErrorState', () => {
  it('shows a Persian sentence, never a status code', () => {
    render(<ErrorState message="مشکلی در سرور پیش آمد. لطفاً بعداً دوباره تلاش کنید." />)

    expect(screen.getByRole('alert')).toHaveTextContent('مشکلی در سرور پیش آمد')
    expect(screen.queryByText(/500/)).toBeNull()
    expect(screen.queryByText(/Internal Server Error/)).toBeNull()
  })

  it('forwards a retry action', async () => {
    const onRetry = vi.fn()
    render(<ErrorState message="خطا" onRetry={onRetry} />)

    await userEvent.click(screen.getByRole('button', { name: /تلاش دوباره/ }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })
})

// ---------------------------------------------------------------------------

describe('BudgetProgress', () => {
  it('does not display the server commentary sentence', () => {
    // The card carries the numbers (spent, remaining, percentage); the
    // sentence underneath was removed as redundant with the status badge.
    render(
      <BudgetProgress
        analysis={makeAnalysis({
          message: 'وضعیت مناسب — مصرف شما از سرعت گذر ماه کمتر است.',
        })}
      />,
    )

    expect(
      screen.queryByText('وضعیت مناسب — مصرف شما از سرعت گذر ماه کمتر است.'),
    ).not.toBeInTheDocument()
  })

  it('never uses accusatory language', () => {
    const statuses = ['safe', 'normal', 'near_limit', 'over'] as const

    for (const status of statuses) {
      const { container, unmount } = render(
        <BudgetProgress
          analysis={makeAnalysis({
            status,
            message:
              status === 'over'
                ? 'بودجه تعیین‌شده برای این دسته تمام شده است.'
                : 'وضعیت مناسب — مصرف شما از سرعت گذر ماه کمتر است.',
          })}
        />,
      )

      // The product principle forbids blaming the user.
      expect(container.textContent).not.toMatch(/ضعیف|بی‌دقت|اشتباه کرده‌اید|ناموفق/)
      unmount()
    }
  })

  it('renders the status label as text alongside the colour', () => {
    render(<BudgetProgress analysis={makeAnalysis({ status: 'over', status_label: 'بیش از بودجه' })} />)
    expect(screen.getByText('بیش از بودجه')).toBeInTheDocument()
  })

  it('highlights the over-budget amount when the budget is exceeded', () => {
    render(
      <BudgetProgress
        analysis={makeAnalysis({
          status: 'over',
          status_label: 'بیش از بودجه',
          over_budget_amount: '200000.00',
          over_budget_display: '۲۰۰٬۰۰۰ تومان',
        })}
      />,
    )

    expect(screen.getByText(/بیش از بودجه:/)).toBeInTheDocument()
  })

  it('shows the remaining amount when there is still room', () => {
    render(<BudgetProgress analysis={makeAnalysis()} />)
    expect(screen.getByText(/باقی‌مانده:/)).toBeInTheDocument()
  })

  it('renders the consumed percentage in the product numeral style', () => {
    render(<BudgetProgress analysis={makeAnalysis({ consumed_percent: '40.00' })} />)
    expect(screen.getByText('40%')).toBeInTheDocument()
  })

  it('labels its progress bar with the category name', () => {
    render(<BudgetProgress analysis={makeAnalysis()} />)
    expect(
      screen.getByRole('progressbar', { name: 'میزان مصرف بودجه خوراک' }),
    ).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------

describe('JalaliDatePicker', () => {
  it('shows the selected date in Persian', () => {
    render(
      <JalaliDatePicker value="2026-09-20" onChange={() => {}} label="تاریخ" />,
    )
    // Jalali month name in Persian, digits in the product's numeral style.
    expect(screen.getByText('29 شهریور 1405')).toBeInTheDocument()
  })

  it('opens a real Jalali calendar with the weekday header', async () => {
    render(<JalaliDatePicker value="2026-09-20" onChange={() => {}} label="تاریخ" />)

    await userEvent.click(screen.getByRole('button', { expanded: false }))

    // شنبه first, not Sunday — this is a Jalali calendar, not a gregorian one.
    expect(screen.getByText('ش')).toBeInTheDocument()
    expect(screen.getByLabelText('ماه')).toBeInTheDocument()
    expect(screen.getByLabelText('سال')).toBeInTheDocument()
  })

  it('returns an ISO Gregorian date, never a Jalali one', async () => {
    const onChange = vi.fn()
    render(<JalaliDatePicker value="2026-09-20" onChange={onChange} label="تاریخ" />)

    await userEvent.click(screen.getByRole('button', { expanded: false }))

    // The picker opens on شهریور ۱۴۰۵. Its grid is a full rectangle, so the
    // first row is the tail of مرداد. Day 1 of شهریور ۱۴۰۵ falls on
    // 2026-08-23 — a <b>یکشنبه</b>, and the ZWNJ inside the weekday name
    // matters for label matching. Digits are Latin, names stay Persian.
    await userEvent.click(screen.getByLabelText('یک‌شنبه 1 شهریور 1405'))

    // Each day cell carries the Gregorian ISO for its Jalali date: the 1st of
    // شهریور ۱۴۰۵ is 2026-08-23.
    expect(onChange).toHaveBeenCalledWith('2026-08-23')
  })

  it('disables future days when asked to', async () => {
    render(
      <JalaliDatePicker value="2026-09-20" onChange={() => {}} label="تاریخ" disableFuture />,
    )

    await userEvent.click(screen.getByRole('button', { expanded: false }))

    // Every day button after today must be disabled. Day cells are numeral
    // buttons, so match the digit style the product actually renders.
    const buttons = screen.getAllByRole('button')
    const disabledDays = buttons.filter(
      (button) => button.hasAttribute('disabled') && /^[0-9]+$/.test((button.textContent ?? '').trim()),
    )
    expect(disabledDays.length).toBeGreaterThan(0)
  })

  it('opens on the selected month', async () => {
    render(<JalaliDatePicker value="2026-09-20" onChange={() => {}} label="تاریخ" />)

    await userEvent.click(screen.getByRole('button', { expanded: false }))

    expect(screen.getByLabelText('ماه')).toHaveValue('6')
    expect(screen.getByLabelText('سال')).toHaveValue('1405')
  })
})
