import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'
import type { User } from '@/types'

interface AuthState {
  user: User | null
  accessToken: string | null
}

interface AuthContextValue extends AuthState {
  login: (token: string, user: User) => void
  logout: () => void
  setToken: (token: string) => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

// Module-level token store so apiFetch can read it without React context
let _currentToken: string | null = null
export const getStoredToken = () => _currentToken
export const setStoredToken = (t: string | null) => { _currentToken = t }

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
          // Fetch /me to get user info
          const meRes = await fetch('/api/auth/me', {
            headers: { Authorization: `Bearer ${data.access_token}` },
          })
          if (meRes.ok) {
            const user = await meRes.json()
            setState({ accessToken: data.access_token, user: { id: user.user_id, email: user.email, resend_domain: user.resend_domain, created_at: user.created_at } })
          }
        }
      })
      .catch(() => {})
      .finally(() => setInitializing(false))
  }, [])

  const login = useCallback((token: string, user: User) => {
    setStoredToken(token)
    setState({ accessToken: token, user })
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

  if (initializing) return <div className="flex items-center justify-center min-h-screen"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" /></div>

  return (
    <AuthContext.Provider value={{ ...state, login, logout, setToken }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
