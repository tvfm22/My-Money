/**
 * The one HTTP client.
 *
 * Responsibilities:
 *   * attach the access token to every request;
 *   * transparently refresh an expired access token once, then replay the
 *     original request — so a user never sees a spurious "logged out" state
 *     just because a token aged out mid-session;
 *   * serialise concurrent refreshes, so ten parallel queries that all 401 at
 *     once trigger exactly one refresh instead of ten;
 *   * surface errors as a predictable `ApiError` shape with a Persian message,
 *     so no component has to inspect a raw axios error.
 */

import axios, {
  AxiosError,
  type AxiosInstance,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from 'axios'

import type { ApiError } from '../types'
import { latinizeDeep } from '../utils/format'

const ACCESS_TOKEN_KEY = 'mymoney.access'
const REFRESH_TOKEN_KEY = 'mymoney.refresh'

// ---------------------------------------------------------------------------
// Token storage
// ---------------------------------------------------------------------------

/**
 * Tokens live in `localStorage` rather than memory so a refresh keeps the user
 * signed in. This is a deliberate trade-off for a personal finance SPA with no
 * server-rendered surface; the API is the only thing that can be reached with
 * a stolen token, and tokens are short-lived and rotated.
 */
export const tokenStore = {
  getAccess(): string | null {
    try {
      return window.localStorage.getItem(ACCESS_TOKEN_KEY)
    } catch {
      return null
    }
  },

  getRefresh(): string | null {
    try {
      return window.localStorage.getItem(REFRESH_TOKEN_KEY)
    } catch {
      return null
    }
  },

  set(access: string, refresh?: string): void {
    try {
      window.localStorage.setItem(ACCESS_TOKEN_KEY, access)
      if (refresh) window.localStorage.setItem(REFRESH_TOKEN_KEY, refresh)
    } catch {
      /* Storage unavailable (private mode). The session simply will not persist. */
    }
  },

  clear(): void {
    try {
      window.localStorage.removeItem(ACCESS_TOKEN_KEY)
      window.localStorage.removeItem(REFRESH_TOKEN_KEY)
    } catch {
      /* nothing to do */
    }
  },
}

/** Notified when the session ends and the user must be sent back to login. */
type SessionExpiredHandler = () => void
let onSessionExpired: SessionExpiredHandler | null = null

export function setSessionExpiredHandler(handler: SessionExpiredHandler | null): void {
  onSessionExpired = handler
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'

export const http: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  // Django sets an HttpOnly CSRF cookie for session auth; JWT requests do not
  // need it, but sending credentials keeps the door open for both.
  withCredentials: false,
  timeout: 20_000,
})

http.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = tokenStore.getAccess()
  if (token) {
    config.headers.set('Authorization', `Bearer ${token}`)
  }
  return config
})

/**
 * A single in-flight refresh, shared by every request that 401s while it runs.
 * Without this, a page that fires six queries on mount would attempt six
 * refreshes and rotate the token six times, invalidating five of them.
 */
let refreshPromise: Promise<string> | null = null

async function refreshAccessToken(): Promise<string> {
  const refresh = tokenStore.getRefresh()
  if (!refresh) throw new Error('no-refresh-token')

  // A bare axios call, not `http`, so a failing refresh cannot re-enter this
  // interceptor and loop.
  const response = await axios.post<{ access: string; refresh?: string }>(
    `${API_BASE_URL}/auth/token/refresh/`,
    { refresh },
    { headers: { 'Content-Type': 'application/json' } },
  )

  const { access, refresh: rotated } = response.data
  tokenStore.set(access, rotated ?? refresh)
  return access
}

interface RetryableConfig extends AxiosRequestConfig {
  _retried?: boolean
}

http.interceptors.response.use(
  (response) => {
    // Every server-provided `*_display` string carries Persian digits. The
    // product renders numerals in Latin, so they are transliterated here —
    // once, for the whole app — instead of at ~50 render sites. Values are not
    // recomputed, only their digits rewritten, so the client and server can
    // never disagree about an amount.
    response.data = latinizeDeep(response.data)
    return response
  },
  async (error: AxiosError) => {
    const config = error.config as RetryableConfig | undefined
    const status = error.response?.status

    const isRefreshable =
      status === 401 &&
      config &&
      !config._retried &&
      // Never try to refresh the refresh call itself.
      !config.url?.includes('/auth/token/refresh/') &&
      !config.url?.includes('/auth/login/')

    if (isRefreshable) {
      config._retried = true

      try {
        if (!refreshPromise) {
          refreshPromise = refreshAccessToken().finally(() => {
            refreshPromise = null
          })
        }
        const access = await refreshPromise
        config.headers = { ...config.headers, Authorization: `Bearer ${access}` }
        return http.request(config)
      } catch {
        tokenStore.clear()
        onSessionExpired?.()
        return Promise.reject(normalizeError(error))
      }
    }

    if (status === 401) {
      // Unauthenticated and not recoverable.
      tokenStore.clear()
    }

    return Promise.reject(normalizeError(error))
  },
)

// ---------------------------------------------------------------------------
// Error normalisation
// ---------------------------------------------------------------------------

/**
 * Does this string read as a message we can show a Persian-speaking user?
 *
 * The backend localises everything it authors, so a genuine server `detail`
 * contains Persian script. A bare `"Internal Server Error"`, a stack-trace
 * fragment, or a raw exception class name does not — and the product spec is
 * explicit that those must never reach the screen. Rather than trusting any
 * non-empty `detail`, we require Persian characters before showing it and fall
 * back to our own copy otherwise.
 */
function isPersianMessage(value: unknown): value is string {
  return typeof value === 'string' && /[\u0600-\u06FF]/.test(value)
}

/**
 * Is this value an `ApiError` this module already produced?
 *
 * A structural check rather than `instanceof`, because the value crosses a
 * `Promise.reject` boundary and may be constructed in another module instance
 * during a hot reload — an identity check would then wrongly miss.
 */
function isApiError(value: unknown): value is ApiError {
  if (typeof value !== 'object' || value === null) return false
  const candidate = value as Partial<ApiError>
  return (
    isPersianMessage(candidate.detail) &&
    // `status` is absent on the network-failure variant, so only its type is
    // constrained, not its presence.
    (candidate.status === undefined || typeof candidate.status === 'number')
  )
}

/**
 * Turn any failure into an `ApiError` with a Persian, user-facing `detail`.
 *
 * The server already localises its own messages, so a server-provided detail
 * is passed through untouched. This only fills in the cases the server could
 * not speak to: a dead network, a timeout, a 500 with no body.
 */
export function normalizeError(error: unknown): ApiError {
  // Already normalised. The response interceptor rejects with an `ApiError`
  // (a plain object, not an Error subclass), and callers routinely hand that
  // value back to `errorMessage`/`fieldErrors`. Without this branch the second
  // pass fell through to the final fallback, so *every* server-authored
  // message was replaced by "خطای ناشناختهای رخ داد." That silently discarded
  // the localised detail the backend had already produced.
  if (isApiError(error)) {
    return error
  }

  if (axios.isAxiosError(error)) {
    const data = error.response?.data as ApiError | undefined
    const status = error.response?.status

    // Prefer the server's message, but only when it is actually Persian. An
    // untranslated "Internal Server Error" must fall through to our own copy
    // rather than be shown verbatim.
    if (isPersianMessage(data?.detail)) {
      return { detail: data.detail, errors: data.errors, status }
    }

    if (error.code === 'ECONNABORTED') {
      return { detail: 'پاسخی از سرور دریافت نشد. دوباره تلاش کنید.', status: undefined }
    }

    if (!error.response) {
      return { detail: 'ارتباط با سرور برقرار نشد. اتصال اینترنت خود را بررسی کنید.' }
    }

    if (status !== undefined && status >= 500) {
      // A 5xx with no usable body: the server is at fault, not the user.
      return {
        detail: 'مشکلی در سرور پیش آمد. لطفاً بعداً دوباره تلاش کنید.',
        // Field errors are still worth keeping — a 5xx can carry a partial
        // validation report, and losing it would hide the actionable part.
        errors: data?.errors,
        status,
      }
    }
    if (status === 404) {
      return { detail: 'موردی که دنبالش بودید پیدا نشد.', status }
    }
    if (status === 403) {
      return { detail: 'شما اجازه دسترسی به این اطلاعات را ندارید.', status }
    }

    return { detail: 'خطایی رخ داد. دوباره تلاش کنید.', status }
  }

  if (error instanceof Error) {
    return { detail: error.message }
  }

  return { detail: 'خطای ناشناخته‌ای رخ داد.' }
}

/** Convenience: the Persian message from any thrown value. */
export function errorMessage(error: unknown, fallback = 'خطایی رخ داد.'): string {
  return normalizeError(error).detail || fallback
}

/** Field-level errors, shaped for React Hook Form's `setError`. */
export function fieldErrors(error: unknown): Record<string, string> {
  const normalized = normalizeError(error)
  const result: Record<string, string> = {}
  if (normalized.errors) {
    for (const [field, messages] of Object.entries(normalized.errors)) {
      if (messages.length > 0) result[field] = messages[0]
    }
  }
  return result
}
