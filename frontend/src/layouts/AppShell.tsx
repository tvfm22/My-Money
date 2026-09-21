import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { Menu, Plus, Search, Wallet } from 'lucide-react'
import { useState } from 'react'
import { NAV_ITEMS, NAV_SECTIONS, MOBILE_NAV_ITEMS } from '../config/navigation'
import { useAuth } from '../hooks/useAuth'
import { BottomSheet } from '../components/ui/BottomSheet'
import { QuickExpenseSheet } from '../features/transactions/QuickExpenseSheet'

/**
 * The persistent frame around every authenticated screen.
 *
 * Desktop gets a fixed sidebar; phones get a bottom navigation bar plus a
 * floating "ثبت تراکنش" action, because entering an expense has to be a
 * one-thumb operation.
 */
export function AppShell() {
  const { user } = useAuth()
  const location = useLocation()
  const [isMenuOpen, setIsMenuOpen] = useState(false)
  const [isQuickAddOpen, setIsQuickAddOpen] = useState(false)

  const initials = (user?.display_name || user?.email || '؟').trim().charAt(0)

  return (
    <div className="min-h-dvh bg-canvas">
      {/* ---------------------------------------------------------------- */}
      {/* Desktop sidebar                                                    */}
      {/* ---------------------------------------------------------------- */}
      <aside className="fixed inset-y-0 end-0 z-30 hidden w-64 flex-col border-s border-border bg-surface lg:flex">
        <div className="flex h-16 items-center gap-2.5 px-5">
          <span className="flex size-9 items-center justify-center rounded-control bg-brand-600 text-white">
            <Wallet className="size-4.5" aria-hidden="true" />
          </span>
          <div className="leading-tight">
            <p className="text-[15px] font-bold text-ink">مالی من</p>
            <p className="text-[10.5px] text-ink-faint">مدیریت مالی شخصی</p>
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto px-3 py-2" aria-label="ناوبری اصلی">
          {NAV_SECTIONS.map((section) => {
            const items = NAV_ITEMS.filter((item) => item.section === section.key)
            if (items.length === 0) return null

            return (
              <div key={section.key} className="mb-4">
                <p className="px-3 pb-1.5 text-[10.5px] font-medium tracking-wide text-ink-faint">
                  {section.label}
                </p>
                <ul className="space-y-0.5">
                  {items.map((item) => (
                    <li key={item.to}>
                      <NavLink
                        to={item.to}
                        end={item.to === '/'}
                        className={({ isActive }) =>
                          [
                            'flex h-10 items-center gap-2.5 rounded-control px-3 text-[13.5px] font-medium transition-colors',
                            isActive
                              ? 'bg-brand-50 text-brand-700'
                              : 'text-ink-soft hover:bg-surface-muted hover:text-ink',
                          ].join(' ')
                        }
                      >
                        <item.icon className="size-4.5 shrink-0" aria-hidden="true" />
                        {item.label}
                      </NavLink>
                    </li>
                  ))}
                </ul>
              </div>
            )
          })}
        </nav>

        <div className="border-t border-border p-3">
          <button
            type="button"
            onClick={() => setIsQuickAddOpen(true)}
            className="flex h-11 w-full items-center justify-center gap-2 rounded-control bg-brand-600 text-sm font-semibold text-white transition-colors hover:bg-brand-700"
          >
            <Plus className="size-4" aria-hidden="true" />
            ثبت تراکنش
          </button>
        </div>
      </aside>

      {/* ---------------------------------------------------------------- */}
      {/* Mobile top bar                                                     */}
      {/* ---------------------------------------------------------------- */}
      <header className="sticky top-0 z-20 border-b border-border bg-surface/85 backdrop-blur lg:hidden">
        <div className="flex h-14 items-center justify-between gap-3 px-4">
          <div className="flex items-center gap-2">
            <span className="flex size-8 items-center justify-center rounded-control bg-brand-600 text-white">
              <Wallet className="size-4" aria-hidden="true" />
            </span>
            <span className="text-sm font-bold text-ink">مالی من</span>
          </div>

          <div className="flex items-center gap-1">
            <NavLink
              to="/transactions?focus=search"
              aria-label="جست‌وجو در تراکنش‌ها"
              className="flex size-11 items-center justify-center rounded-control text-ink-soft transition-colors hover:bg-surface-muted active:bg-surface-muted"
            >
              <Search className="size-5" aria-hidden="true" />
            </NavLink>

            <button
              type="button"
              onClick={() => setIsMenuOpen(true)}
              aria-label="فهرست"
              className="flex size-11 items-center justify-center rounded-control text-ink-soft transition-colors hover:bg-surface-muted active:bg-surface-muted"
            >
              {initials ? (
                <span className="flex size-7 items-center justify-center rounded-pill bg-brand-100 text-[12px] font-semibold text-brand-700">
                  {initials}
                </span>
              ) : (
                <Menu className="size-5" aria-hidden="true" />
              )}
            </button>
          </div>
        </div>
      </header>

      {/* ---------------------------------------------------------------- */}
      {/* Routed content                                                     */}
      {/* ---------------------------------------------------------------- */}
      <main className="lg:pe-64">
        <div key={location.pathname} className="mx-auto w-full max-w-3xl px-4 pt-4 pb-bottom-nav lg:max-w-4xl lg:px-8 lg:pt-6 lg:pb-10">
          <Outlet />
        </div>
      </main>

      {/* ---------------------------------------------------------------- */}
      {/* Mobile bottom navigation                                           */}
      {/* ---------------------------------------------------------------- */}
      <nav
        className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-surface/95 backdrop-blur lg:hidden"
        aria-label="ناوبری اصلی"
      >
        <ul className="mx-auto flex max-w-lg items-stretch justify-around pb-[env(safe-area-inset-bottom)]">
          {MOBILE_NAV_ITEMS.map((item) => (
            <li key={item.to} className="flex-1">
              <NavLink
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) =>
                  [
                    'flex h-14 min-h-[44px] flex-col items-center justify-center gap-1 transition-colors',
                    isActive ? 'text-brand-600' : 'text-ink-faint',
                  ].join(' ')
                }
              >
                {({ isActive }) => (
                  <>
                    <item.icon className="size-5" aria-hidden="true" />
                    <span className={['text-[10.5px]', isActive ? 'font-semibold' : ''].join(' ')}>
                      {item.label}
                    </span>
                  </>
                )}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      {/* Floating quick-add — sits above the bottom nav, within thumb reach. */}
      <button
        type="button"
        onClick={() => setIsQuickAddOpen(true)}
        className="fixed bottom-[calc(4.5rem+env(safe-area-inset-bottom))] end-4 z-30 flex size-14 items-center justify-center rounded-pill bg-brand-600 text-white shadow-overlay transition-transform active:scale-95 lg:hidden"
        aria-label="ثبت تراکنش جدید"
      >
        <Plus className="size-6" aria-hidden="true" />
      </button>

      {/* Overflow menu for the sections that don't fit in the bottom nav. */}
      <BottomSheet open={isMenuOpen} onClose={() => setIsMenuOpen(false)} title="فهرست">
        <ul className="space-y-1">
          {NAV_ITEMS.filter((item) => !item.inBottomNav).map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                onClick={() => setIsMenuOpen(false)}
                className={({ isActive }) =>
                  [
                    'flex h-12 items-center gap-3 rounded-control px-3 text-sm font-medium transition-colors',
                    isActive ? 'bg-brand-50 text-brand-700' : 'text-ink-soft hover:bg-surface-muted',
                  ].join(' ')
                }
              >
                <item.icon className="size-5" aria-hidden="true" />
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>

        <div className="mt-4 border-t border-border pt-4">
          <NavLink
            to="/profile"
            onClick={() => setIsMenuOpen(false)}
            className="flex items-center justify-between rounded-control px-3 py-2.5 text-sm text-ink-soft hover:bg-surface-muted"
          >
            <span>حساب کاربری</span>
            <span className="text-xs text-ink-faint" dir="ltr">
              {user?.email}
            </span>
          </NavLink>
        </div>
      </BottomSheet>

      <QuickExpenseSheet open={isQuickAddOpen} onClose={() => setIsQuickAddOpen(false)} />
    </div>
  )
}
