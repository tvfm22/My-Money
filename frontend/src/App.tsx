import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import type { ReactNode } from 'react'
import { AppShell } from './layouts/AppShell'
import { AuthPage } from './features/auth/AuthPage'
import { DashboardPage } from './features/dashboard/DashboardPage'
import { TransactionsPage } from './features/transactions/TransactionsPage'
import { BudgetsPage } from './features/budgets/BudgetsPage'
import { BudgetPerformancePage } from './features/budgets/BudgetPerformancePage'
import { DebtsPage } from './features/debts/DebtsPage'
import { DebtDetailPage } from './features/debts/DebtDetailPage'
import { InsightsPage } from './features/insights/InsightsPage'
import { SettingsPage } from './features/settings/SettingsPage'
import { useAuth } from './hooks/useAuth'
import { FullPageLoader } from './components/layout/FullPageLoader'
import { LoadingCard } from './components/ui/LoadingState'

/**
 * Reports is the only route that pulls in a charting library, so it is split
 * out of the main bundle. Everything else ships on first load; the ~400 kB of
 * Recharts only arrives if the user actually opens a chart.
 */
const ReportsPage = lazy(() =>
  import('./features/reports/ReportsPage').then((module) => ({ default: module.ReportsPage })),
)

/** Assets draws the net-worth trend, so it is split for the same reason. */
const AssetsPage = lazy(() =>
  import('./features/assets/AssetsPage').then((module) => ({ default: module.AssetsPage })),
)

/** Sends unauthenticated visitors to the login screen, remembering where they were headed. */
function RequireAuth({ children }: { children: ReactNode }) {
  const { isAuthenticated, isBootstrapping } = useAuth()
  const location = useLocation()

  if (isBootstrapping) return <FullPageLoader />

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  }

  return <>{children}</>
}

/** Keeps signed-in users away from the auth screen. */
function RedirectIfAuthed({ children }: { children: ReactNode }) {
  const { isAuthenticated, isBootstrapping } = useAuth()

  if (isBootstrapping) return <FullPageLoader />
  if (isAuthenticated) return <Navigate to="/" replace />

  return <>{children}</>
}

function NotFound() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 text-center">
      <p className="text-3xl font-bold text-ink">404</p>
      <p className="text-sm text-ink-soft">صفحه‌ای که دنبال آن بودید پیدا نشد.</p>
      <a href="/" className="text-sm font-medium text-brand-600 hover:text-brand-700">
        بازگشت به خانه
      </a>
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      <Route
        path="/login"
        element={
          <RedirectIfAuthed>
            <AuthPage />
          </RedirectIfAuthed>
        }
      />

      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="transactions" element={<TransactionsPage />} />
        <Route path="budgets" element={<BudgetsPage />} />
        <Route path="budgets/performance" element={<BudgetPerformancePage />} />
        <Route path="debts" element={<DebtsPage />} />
        <Route path="debts/:id" element={<DebtDetailPage />} />
        <Route
          path="assets"
          element={
            <Suspense
              fallback={
                <div className="space-y-4">
                  <LoadingCard />
                  <LoadingCard />
                </div>
              }
            >
              <AssetsPage />
            </Suspense>
          }
        />
        <Route
          path="reports"
          element={
            <Suspense
              fallback={
                <div className="space-y-4">
                  <LoadingCard />
                  <LoadingCard />
                </div>
              }
            >
              <ReportsPage />
            </Suspense>
          }
        />
        <Route path="insights" element={<InsightsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
