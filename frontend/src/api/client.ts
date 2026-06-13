import { getStoredToken, setStoredToken } from '@/contexts/AuthContext'
import type { ApiError } from '@/types'

const BASE = '/api'

let _refreshPromise: Promise<string> | null = null

async function refreshToken(): Promise<string> {
  if (_refreshPromise) return _refreshPromise
  _refreshPromise = fetch(`${BASE}/auth/refresh`, { method: 'POST', credentials: 'include' })
    .then(async (res) => {
      if (!res.ok) throw new Error('Refresh failed')
      const data = await res.json()
      setStoredToken(data.access_token)
      return data.access_token as string
    })
    .finally(() => { _refreshPromise = null })
  return _refreshPromise
}

export async function apiFetch<T = unknown>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getStoredToken()
  const isFormData = options.body instanceof FormData
  const headers: Record<string, string> = {
    // Let the browser set the multipart boundary for FormData uploads.
    ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
    ...(options.headers as Record<string, string> ?? {}),
  }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${BASE}${path}`, { ...options, headers, credentials: 'include' })

  if (res.status === 401) {
    try {
      const newToken = await refreshToken()
      headers['Authorization'] = `Bearer ${newToken}`
      const retry = await fetch(`${BASE}${path}`, { ...options, headers, credentials: 'include' })
      if (retry.ok) return retry.json() as Promise<T>
      // Second 401 — clear token and redirect
      setStoredToken(null)
      window.location.href = '/login'
      throw new Error('Session expired')
    } catch {
      setStoredToken(null)
      window.location.href = '/login'
      throw new Error('Session expired')
    }
  }

  if (!res.ok) {
    let errBody: ApiError = { error: 'Request failed', code: 'UNKNOWN' }
    try {
      const parsed = await res.json()
      // FastAPI nests our error payload under `detail`.
      errBody = (parsed?.detail ?? parsed) as ApiError
    } catch {}
    // A member who still owes a forced password reset is bounced to the reset
    // screen for any protected call.
    if (res.status === 403 && errBody.code === 'PASSWORD_CHANGE_REQUIRED'
        && window.location.pathname !== '/change-password') {
      window.location.href = '/change-password'
    }
    throw errBody
  }

  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}
