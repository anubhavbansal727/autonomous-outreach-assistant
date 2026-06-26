import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import { apiFetch } from '@/api/client'
import { PERMISSIONS } from '@/lib/permissions'
import { Button, buttonVariants } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export function SettingsPage() {
  const { user, logout, refreshMe, can } = useAuth()
  const canManage = can(PERMISSIONS.TENANT_MANAGE)

  const [name, setName] = useState(user?.tenant?.name ?? '')
  const [domain, setDomain] = useState(user?.tenant?.resend_domain ?? '')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault(); setSaving(true); setSaved(false); setError('')
    try {
      await apiFetch('/tenant', { method: 'PATCH', body: JSON.stringify({ name, resend_domain: domain }) })
      await refreshMe()
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (err: unknown) {
      setError((err as { error?: string })?.error ?? 'Failed to save workspace settings')
    } finally { setSaving(false) }
  }

  return (
    <div className="max-w-xl space-y-6">
      <h1 className="text-2xl font-bold">Settings</h1>

      <Card>
        <CardHeader><CardTitle>Account</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div><p className="text-sm text-muted-foreground">Email</p><p className="font-medium">{user?.email}</p></div>
          <div className="flex items-center gap-2">
            <p className="text-sm text-muted-foreground">Role</p>
            {user?.role && <Badge variant="secondary" className="capitalize">{user.role}</Badge>}
          </div>
          <div className="flex gap-2">
            <Link to="/change-password" className={buttonVariants({ variant: 'outline' })}>Change password</Link>
            <Button variant="outline" onClick={logout}>Log out</Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Workspace</CardTitle></CardHeader>
        <CardContent>
          {canManage ? (
            <form onSubmit={handleSave} className="space-y-4">
              <div className="space-y-1">
                <Label>Workspace name</Label>
                <Input value={name} onChange={e => setName(e.target.value)} placeholder="Acme Inc" />
              </div>
              <div className="space-y-1">
                <Label>Resend sending domain</Label>
                <Input value={domain} onChange={e => setDomain(e.target.value)} placeholder="yourdomain.com" />
                <p className="text-xs text-muted-foreground">Shared by everyone in the workspace. Must be verified in Resend before sending.</p>
              </div>
              {saved && <p className="text-sm text-green-600">Saved!</p>}
              {error && <p className="text-sm text-destructive">{error}</p>}
              <Button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save workspace'}</Button>
            </form>
          ) : (
            <div className="space-y-3 text-sm">
              <div><p className="text-muted-foreground">Workspace name</p><p className="font-medium">{user?.tenant?.name ?? '—'}</p></div>
              <div><p className="text-muted-foreground">Sending domain</p><p className="font-medium">{user?.tenant?.resend_domain ?? 'Not configured'}</p></div>
              <p className="text-xs text-muted-foreground">Only an owner can change workspace settings.</p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
