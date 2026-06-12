import { useState } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import { apiFetch } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export function SettingsPage() {
  const { user, logout } = useAuth()
  const [domain, setDomain] = useState(user?.resend_domain ?? '')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  const handleSaveDomain = async (e: React.FormEvent) => {
    e.preventDefault(); setSaving(true); setSaved(false); setError('')
    try {
      await apiFetch('/auth/me', { method: 'PATCH', body: JSON.stringify({ resend_domain: domain }) })
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (err: unknown) {
      setError((err as { error?: string })?.error ?? 'Failed to save domain')
    }
    finally { setSaving(false) }
  }

  return (
    <div className="max-w-xl space-y-6">
      <h1 className="text-2xl font-bold">Settings</h1>
      <Card>
        <CardHeader><CardTitle>Account</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div><p className="text-sm text-muted-foreground">Email</p><p className="font-medium">{user?.email}</p></div>
          <Button variant="outline" onClick={logout}>Log out</Button>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Email sending domain</CardTitle></CardHeader>
        <CardContent>
          <form onSubmit={handleSaveDomain} className="space-y-3">
            <div className="space-y-1">
              <Label>Resend sending domain</Label>
              <Input value={domain} onChange={e => setDomain(e.target.value)} placeholder="yourdomain.com" />
              <p className="text-xs text-muted-foreground">Must be verified in your Resend account before sending emails.</p>
            </div>
            {saved && <p className="text-sm text-green-600">Saved!</p>}
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button type="submit" disabled={saving}>{saving ? 'Saving...' : 'Save domain'}</Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
