import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import { AuthProvider } from './hooks/useAuth.tsx'
import { ThemeProvider } from './hooks/useTheme.tsx'
import { ToastProvider } from './components/ui/Toast.tsx'
import { normalizeError } from './services/client.ts'

/**
 * Query defaults.
 *
 * Two deliberate choices:
 *  - `retry` will not retry a 4xx. Re-sending a request the server has already
 *    rejected wastes the user's time and hides the real message.
 *  - `refetchOnWindowFocus` stays on so returning to an idle tab shows fresh
 *    numbers — this is a finance app, stale balances are worse than a fetch.
 */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 10 * 60_000,
      refetchOnWindowFocus: true,
      retry: (failureCount, error) => {
        const normalized = normalizeError(error)
        if (normalized.status && normalized.status >= 400 && normalized.status < 500) {
          return false
        }
        return failureCount < 2
      },
    },
    mutations: {
      // A failed write is surfaced immediately; retrying silently could
      // double-post a transaction.
      retry: false,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ThemeProvider>
          <AuthProvider>
            <ToastProvider>
              <App />
            </ToastProvider>
          </AuthProvider>
        </ThemeProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
