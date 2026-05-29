import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import { apiFetch } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { login } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(''); setLoading(true)
    try {
      const data = await apiFetch<{ access_token: string; user_id: string }>('/auth/login', {
        method: 'POST', body: JSON.stringify({ email, password }),
      })
      const me = await apiFetch<{ user_id: string; email: string; resend_domain: string | null; created_at: string }>('/auth/me', {
        headers: { Authorization: `Bearer ${data.access_token}` },
      })
      login(data.access_token, { id: me.user_id, email: me.email, resend_domain: me.resend_domain, created_at: me.created_at })
      navigate('/')
    } catch (err: unknown) {
      setError((err as { error?: string })?.error ?? 'Login failed')
    } finally { setLoading(false) }
  }

  return (
    <div className="flex items-center justify-center min-h-screen bg-muted/30">
      <Card className="w-full max-w-sm">
        <CardHeader><CardTitle>Sign in</CardTitle></CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1"><Label>Email</Label><Input type="email" value={email} onChange={e => setEmail(e.target.value)} required /></div>
            <div className="space-y-1"><Label>Password</Label><Input type="password" value={password} onChange={e => setPassword(e.target.value)} required /></div>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button type="submit" className="w-full" disabled={loading}>{loading ? 'Signing in…' : 'Sign in'}</Button>
            <p className="text-sm text-center text-muted-foreground">No account? <Link to="/register" className="text-primary hover:underline">Register</Link></p>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
