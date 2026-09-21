/**
 * Accessibility regression tests.
 *
 * Every form control must have an accessible name. This is easy to get wrong
 * in a component library that renders its own `<label>`: if the `htmlFor`/`id`
 * pair breaks, the field still *looks* labelled, so only a query like
 * `getByLabelText` reveals the problem.
 *
 * These tests exist because that exact bug shipped twice — once in
 * `Input`/`Select`, once in `JalaliDatePicker` with a hardcoded id.
 */

import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'

import { TransactionForm } from '../features/transactions/TransactionForm'
import { DebtForm } from '../features/debts/DebtForm'
import { AccountForm } from '../features/settings/AccountForm'
import { AssetForm } from '../features/assets/AssetForm'
import { QuickExpenseSheet } from '../features/transactions/QuickExpenseSheet'
import { JalaliDatePicker } from '../components/ui/JalaliDatePicker'
import { Input } from '../components/ui/Input'
import { Select } from '../components/ui/Select'
import { type ServerStub, installServerStub, makeWrapper } from './harness'

let server: ServerStub

beforeEach(() => {
  server = installServerStub()
})

afterEach(() => {
  server.restore()
})

/**
 * Assert every focusable control in the container has a name.
 *
 * `getByRole` with a name filter is the accessibility tree's own view — much
 * stronger than checking for a `for`/`id` pair, because it is exactly what a
 * screen reader would announce.
 */
function expectEveryControlNamed(container: HTMLElement = document.body) {
  // Modals and sheets render through a portal, so their controls live in
  // `document.body` rather than inside the `render()` container. Defaulting to
  // the body keeps this helper correct for both inline and portalled markup.
  const controls = container.querySelectorAll<HTMLElement>(
    'input:not([type="hidden"]), select, textarea',
  )
  expect(controls.length).toBeGreaterThan(0)

  const unnamed: string[] = []
  for (const control of controls) {
    const id = control.id
    const type = control.getAttribute('type') ?? control.tagName.toLowerCase()

    let named = false

    // aria-label / aria-labelledby
    if (control.getAttribute('aria-label')?.trim()) named = true
    if (control.getAttribute('aria-labelledby')) named = true

    // An associated <label for>
    if (!named && id) {
      if (container.querySelector(`label[for="${CSS.escape(id)}"]`)) named = true
    }

    // A wrapping <label>
    if (!named && control.closest('label')) named = true

    if (!named) {
      const hint = control.getAttribute('placeholder') ?? control.textContent ?? ''
      unnamed.push(`<${type}> id=${id || '(none)'} placeholder=${hint}`)
    }
  }

  expect(unnamed, `controls with no accessible name:/n  ${unnamed.join('\n  ')}`).toEqual([])
}

describe('form control labelling', () => {
  it('gives every Input a name, even without an id or name prop', () => {
    const { container } = render(
      <div>
        <Input label="مبلغ" />
        <Input label="توضیح" name="description" />
        <Input label="یادداشت" id="custom-note" />
      </div>,
    )
    expectEveryControlNamed(container)
  })

  it('gives every Select a name', () => {
    const { container } = render(
      <div>
        <Select label="حساب" options={[{ value: '1', label: 'نقدی' }]} />
        <Select label="دسته" name="category" options={[{ value: '2', label: 'خوراک' }]} />
      </div>,
    )
    expectEveryControlNamed(container)
  })

  it('names both date pickers on a debt form', async () => {
    render(<DebtForm open debt={null} onClose={() => {}} />, {
      wrapper: makeWrapper(),
    })

    // Two pickers share a form. A hardcoded fallback id made the second one
    // unreachable by label.
    expect(await screen.findByLabelText('تاریخ ایجاد بدهی')).toBeInTheDocument()
    expect(screen.getByLabelText('تاریخ سررسید')).toBeInTheDocument()
    expect(screen.getByLabelText('تاریخ ایجاد بدهی')).not.toBe(
      screen.getByLabelText('تاریخ سررسید'),
    )

    expectEveryControlNamed()
  })

  it('gives each of two side-by-side pickers a distinct id and label', () => {
    const { container } = render(
      <div>
        <JalaliDatePicker label="از تاریخ" value="2026-09-20" onChange={() => {}} />
        <JalaliDatePicker label="تا تاریخ" value="2026-09-21" onChange={() => {}} />
      </div>,
    )

    // The picker is a `<button>`, not an `<input>`, so it is outside the
    // control sweep above. It still needs a unique id: that is what makes the
    // rendered `<label htmlFor>` resolve to the right trigger.
    const triggers = Array.from(container.querySelectorAll<HTMLButtonElement>('button[id]'))
    expect(triggers).toHaveLength(2)

    const ids = triggers.map((button) => button.id)
    expect(new Set(ids).size).toBe(2)
    expect(ids.every((id) => id.length > 0)).toBe(true)

    // Each label points at its own trigger, and each trigger is reachable by
    // the text of that label.
    expect(screen.getByLabelText('از تاریخ')).toBe(triggers[0])
    expect(screen.getByLabelText('تا تاریخ')).toBe(triggers[1])
  })

  it('names every control on the transaction form', async () => {
    render(<TransactionForm open transaction={null} onClose={() => {}} />, {
      wrapper: makeWrapper(),
    })
    await screen.findByRole('button', { name: /خوراک/ })
    expectEveryControlNamed()
  })

  it('names every control on the account form', async () => {
    render(<AccountForm open account={null} onClose={() => {}} />, {
      wrapper: makeWrapper(),
    })
    await screen.findByLabelText(/نام حساب/)
    expectEveryControlNamed()
  })

  it('names every control on the asset form', async () => {
    render(<AssetForm open asset={null} onClose={() => {}} />, {
      wrapper: makeWrapper(),
    })
    await screen.findByLabelText(/نام دارایی/)
    expectEveryControlNamed()
  })

  it('names every keypad key on the quick expense sheet', async () => {
    render(<QuickExpenseSheet open onClose={() => {}} />, {
      wrapper: makeWrapper(),
    })
    await screen.findByText('ثبت سریع تراکنش')

    // Keys display the product's numeral style (Latin) and the accessible name
    // must match the glyph on the key, or a screen reader announces a digit the
    // user cannot see.
    for (const digit of ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']) {
      expect(screen.getByRole('button', { name: digit })).toBeInTheDocument()
    }
    expect(screen.getByRole('button', { name: 'حذف رقم' })).toBeInTheDocument()

    expectEveryControlNamed()
  })
})

describe('dialog semantics', () => {
  it('announces the date popover as a dialog once opened', async () => {
    const { container } = render(
      <JalaliDatePicker label="تاریخ" value="2026-09-20" onChange={() => {}} />,
    )

    // A popover that is visually a dialog but not announced as one is invisible
    // to assistive tech.
    const trigger = screen.getByLabelText('تاریخ')
    trigger.click()

    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveAttribute('aria-label', 'انتخاب تاریخ')
    expect(container).toContainElement(dialog)
  })
})
