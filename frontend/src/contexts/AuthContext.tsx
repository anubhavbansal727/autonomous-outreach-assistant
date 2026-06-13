import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'
import type { MeResponse, User } from '@/types'
import { can as canPermission, type Permission } from '@/lib/permissions'

interface AuthState {
  user: User | null
  accessToken: string | null
}

interface AuthContextValue extends AuthState {
  /** Set the token, fetch /me, and populate the user. Returns the loaded user. */
  login: (token: string) => Promise<User>
  logout: () => void
  setToken: (token: string) => void
  /** Re-fetch /me (e.g. after changing password or role). */
  refreshMe: () => Promise<User | null>
  /** UI-only permission check (server is authoritative). */
  can: (permission: Permission) => boolean
}

const AuthContext = createContext<AuthContextValue | null>(null)

// Module-level token store so apiFetch can read it without React context
let _currentToken: string | null = null
export const getStoredToken = () => _currentToken
export const setStoredToken = (t: string | null) => { _currentToken = t }

function mapMe(me: MeResponse): User {
  return {
    id: me.user_id,
    email: me.email,
    resend_domain: me.resend_domain,
    created_at: me.created_at,
    role: me.role,
    permissions: me.permissions ?? [],
    must_change_password: me.must_change_password ?? false,
    tenant: me.tenant ?? null,
  }
}

async function fetchMe(token: string): Promise<User | null> {
  const res = await fetch('/api/auth/me', { headers: { Authorization: `Bearer ${token}` } })
  if (!res.ok) return null
  return mapMe((await res.json()) as MeResponse)
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({ user: null, accessToken: null })
  const [initializing, setInitializing] = useState(true)

  // Silent refresh on mount
  useEffect(() => {
    fetch('/api/auth/refresh', { method: 'POST', credentials: 'include' })
      .then(async (res) => {
        if (res.ok) {
          const data = await res.json()
          setStoredToken(data.access_token)
          const user = await fetchMe(data.access_token)
          if (user) setState({ accessToken: data.access_token, user })
        }
      })
      .catch(() => {})
      .finally(() => setInitializing(false))
  }, [])

  const login = useCallback(async (token: string): Promise<User> => {
    setStoredToken(token)
    const user = await fetchMe(token)
    if (!user) throw new Error('Failed to load profile')
    setState({ accessToken: token, user })
    return user
  }, [])

  const logout = useCallback(() => {
    setStoredToken(null)
    setState({ accessToken: null, user: null })
    fetch('/api/auth/logout', { method: 'POST', credentials: 'include' }).catch(() => {})
  }, [])

  const setToken = useCallback((token: string) => {
    setStoredToken(token)
    setState(prev => ({ ...prev, accessToken: token }))
  }, [])

  const refreshMe = useCallback(async (): Promise<User | null> => {
    const token = getStoredToken()
    if (!token) return null
    const user = await fetchMe(token)
    if (user) setState(prev => ({ ...prev, user }))
    return user
  }, [])

  const can = useCallback(
    (permission: Permission) => canPermission(state.user?.permissions, permission),
    [state.user],
  )

  if (initializing) return <div className="flex items-center justify-center min-h-screen"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" /></div>

  return (
    <AuthContext.Provider value={{ ...state, login, logout, setToken, refreshMe, can }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
