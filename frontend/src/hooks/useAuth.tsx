/**
 * Authentication context.
 *
 * Holds the current user and exposes login / register / logout. The token
 * itself lives in `tokenStore`; this context is about *identity* — who is
 * signed in — so components can render without each one calling `/auth/me/`.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { authApi } from '../services/api'
import { setSessionExpiredHandler, tokenStore } from '../services/client'
import type { User } from '../types'

interface AuthContextValue {
  user: User | null
  /** True until the initial `/auth/me/` check resolves. */
  isBootstrapping: boolean
  isAuthenticated: boolean
  login: (email: string, password: string) => Promise<void>
  register: (payload: {
    email: string
    password: string
    password_confirm: string
    first_name?: string
    last_name?: string
  }) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isBootstrapping, setIsBootstrapping] = useState(true)

  // On mount, if a token exists try to resolve the user. A failed call means
  // the token is stale, so clear it and fall through to the login screen.
  useEffect(() => {
    let cancelled = false

    async function bootstrap() {
      if (!tokenStore.getAccess()) {
        setIsBootstrapping(false)
        return
      }

      try {
        const me = await authApi.me()
        if (!cancelled) setUser(me)
      } catch {
        tokenStore.clear()
        if (!cancelled) setUser(null)
      } finally {
        if (!cancelled) setIsBootstrapping(false)
      }
    }

    void bootstrap()
    return () => {
      cancelled = true
    }
  }, [])

  // When the client gives up on a session (refresh failed), drop the user so
  // the router redirects to login instead of leaving a half-broken screen.
  useEffect(() => {
    setSessionExpiredHandler(() => setUser(null))
    return () => setSessionExpiredHandler(null)
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const response = await authApi.login(email, password)
    tokenStore.set(response.access, response.refresh)
    setUser(response.user)
  }, [])

  const register = useCallback<AuthContextValue['register']>(async (payload) => {
    const response = await authApi.register(payload)
    tokenStore.set(response.access, response.refresh)
    setUser(response.user)
  }, [])

  const logout = useCallback(async () => {
    const refresh = tokenStore.getRefresh()
    // Clear locally first: even if the server call fails, the user is out.
    tokenStore.clear()
    setUser(null)

    if (refresh) {
      try {
        await authApi.logout(refresh)
      } catch {
        // The refresh token may already be blacklisted; nothing to do.
      }
    }
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isBootstrapping,
      isAuthenticated: user !== null,
      login,
      register,
      logout,
    }),
    [user, isBootstrapping, login, register, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used inside <AuthProvider>')
  }
  return context
}
