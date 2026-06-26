import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import { apiFetch } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export function ChangePasswordPage() {
  const { user, accessToken, refreshMe } = useAuth()
  const navigate = useNavigate()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  // Must be signed in to set a password.
  if (!accessToken) return <Navigate to="/login" replace />

  const forced = !!user?.must_change_password

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (next.length < 8) { setError('New password must be at least 8 characters'); return }
    if (next !== confirm) { setError('Passwords do not match'); return }
    setError(''); setLoading(true)
    try {
      await apiFetch('/auth/change-password', {
        method: 'POST',
        body: JSON.stringify({ current_password: current, new_password: next }),
      })
      await refreshMe()  // clears must_change_password
      navigate('/')
    } catch (err: unknown) {
      setError((err as { error?: string })?.error ?? 'Could not change password')
    } finally { setLoading(false) }
  }

  return (
    <div className="flex items-center justify-center min-h-screen bg-muted/30">
      <Card className="w-full max-w-sm">
        <CardHeader><CardTitle>{forced ? 'Set your password' : 'Change password'}</CardTitle></CardHeader>
        <CardContent>
          {forced && (
            <p className="text-sm text-muted-foreground mb-4">
              Your account was created by an admin. Choose a new password to continue.
            </p>
          )}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1">
              <Label>{forced ? 'Temporary password' : 'Current password'}</Label>
              <Input type="password" autoComplete="current-password" autoFocus value={current} onChange={e => setCurrent(e.target.value)} required />
            </div>
            <div className="space-y-1">
              <Label>New password <span className="text-muted-foreground">(min 8 chars)</span></Label>
              <Input type="password" autoComplete="new-password" value={next} onChange={e => setNext(e.target.value)} required />
            </div>
            <div className="space-y-1">
              <Label>Confirm new password</Label>
              <Input type="password" autoComplete="new-password" value={confirm} onChange={e => setConfirm(e.target.value)} required />
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button type="submit" className="w-full" disabled={loading}>{loading ? 'Saving…' : 'Save password'}</Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
