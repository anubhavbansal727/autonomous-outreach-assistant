import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import type { Member, Role } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Loader2, UserPlus, Copy, Check, Ban, RotateCcw, Trash2 } from 'lucide-react'

const ASSIGNABLE: Role[] = ['admin', 'member', 'viewer']

function roleVariant(role: Role) {
  return role === 'owner' ? 'success' : role === 'admin' ? 'warning' : 'secondary'
}

function CreateMemberDialog() {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<Role>('member')
  const [created, setCreated] = useState<{ email: string; temporary_password: string } | null>(null)
  const [copied, setCopied] = useState(false)
  const [err, setErr] = useState('')

  const mutation = useMutation({
    mutationFn: () => apiFetch<{ email: string; temporary_password: string }>('/members', {
      method: 'POST', body: JSON.stringify({ email, role }),
    }),
    onSuccess: (data) => {
      setCreated(data)
      qc.invalidateQueries({ queryKey: ['members'] })
    },
    onError: (e: unknown) => setErr((e as { error?: string })?.error ?? 'Could not create member'),
  })

  const reset = () => { setEmail(''); setRole('member'); setCreated(null); setCopied(false); setErr('') }

  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) reset() }}>
      <DialogTrigger asChild>
        <Button className="gap-2"><UserPlus className="h-4 w-4" />Add member</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>{created ? 'Member created' : 'Add a team member'}</DialogTitle></DialogHeader>
        {created ? (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Share this one-time password with <span className="font-medium text-foreground">{created.email}</span>.
              They'll be asked to set their own password on first login. You won't see it again.
            </p>
            <div className="flex items-center gap-2">
              <code className="flex-1 px-3 py-2 rounded-md bg-muted text-sm font-mono break-all">{created.temporary_password}</code>
              <Button size="sm" variant="outline" onClick={() => { navigator.clipboard?.writeText(created.temporary_password); setCopied(true) }}>
                {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              </Button>
            </div>
            <div className="flex justify-end"><Button onClick={() => { setOpen(false); reset() }}>Done</Button></div>
          </div>
        ) : (
          <form onSubmit={e => { e.preventDefault(); setErr(''); mutation.mutate() }} className="space-y-4">
            <div className="space-y-1">
              <Label>Email</Label>
              <Input type="email" autoFocus value={email} onChange={e => setEmail(e.target.value)} placeholder="colleague@company.com" required />
            </div>
            <div className="space-y-1">
              <Label>Role</Label>
              <select value={role} onChange={e => setRole(e.target.value as Role)}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm capitalize focus:outline-none focus:ring-2 focus:ring-ring">
                {ASSIGNABLE.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
            {err && <p className="text-sm text-destructive">{err}</p>}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
              <Button type="submit" disabled={mutation.isPending || !email}>{mutation.isPending ? 'Creating…' : 'Create member'}</Button>
            </div>
          </form>
        )}
      </DialogContent>
    </Dialog>
  )
}

export function TeamPage() {
  const { user } = useAuth()
  const qc = useQueryClient()

  const { data, isLoading } = useQuery<{ members: Member[] }>({
    queryKey: ['members'],
    queryFn: () => apiFetch('/members'),
  })

  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, string> }) =>
      apiFetch(`/members/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['members'] }),
  })
  const remove = useMutation({
    mutationFn: (id: string) => apiFetch(`/members/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['members'] }),
  })

  const isOwner = user?.role === 'owner'

  return (
    <div className="max-w-3xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Team</h1>
          <p className="text-muted-foreground text-sm">Manage who can access {user?.tenant?.name ?? 'your workspace'}.</p>
        </div>
        <CreateMemberDialog />
      </div>

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex items-center justify-center p-12"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b"><tr className="text-left">
                  {['Email', 'Role', 'Status', ''].map(h => <th key={h} className="px-4 py-3 font-medium text-muted-foreground">{h}</th>)}
                </tr></thead>
                <tbody>
                  {data?.members.map(m => {
                    const isSelf = m.user_id === user?.id
                    const targetOwner = m.role === 'owner'
                    // Admins can't touch owners; nobody can modify themselves here.
                    const locked = isSelf || (targetOwner && !isOwner)
                    return (
                      <tr key={m.membership_id} className="border-b last:border-0">
                        <td className="px-4 py-3 font-medium">{m.email}{isSelf && <span className="text-muted-foreground font-normal"> (you)</span>}</td>
                        <td className="px-4 py-3">
                          {locked ? (
                            <Badge variant={roleVariant(m.role) as 'success' | 'warning' | 'secondary'} className="capitalize">{m.role}</Badge>
                          ) : (
                            <select value={m.role} disabled={patch.isPending}
                              onChange={e => patch.mutate({ id: m.membership_id, body: { role: e.target.value } })}
                              className="h-8 rounded-md border border-input bg-background px-2 text-sm capitalize focus:outline-none focus:ring-2 focus:ring-ring">
                              {/* Only an owner can grant owner. */}
                              {(isOwner ? (['owner', ...ASSIGNABLE] as Role[]) : ASSIGNABLE).map(r => <option key={r} value={r}>{r}</option>)}
                            </select>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <Badge variant={m.status === 'active' ? 'outline' : 'destructive'} className="capitalize">{m.status}</Badge>
                        </td>
                        <td className="px-4 py-3 text-right whitespace-nowrap">
                          {!locked && (
                            <div className="inline-flex gap-1">
                              {m.status === 'active' ? (
                                <Button size="sm" variant="ghost" title="Suspend" disabled={patch.isPending}
                                  onClick={() => patch.mutate({ id: m.membership_id, body: { status: 'suspended' } })}><Ban className="h-4 w-4" /></Button>
                              ) : (
                                <Button size="sm" variant="ghost" title="Reactivate" disabled={patch.isPending}
                                  onClick={() => patch.mutate({ id: m.membership_id, body: { status: 'active' } })}><RotateCcw className="h-4 w-4" /></Button>
                              )}
                              <Button size="sm" variant="ghost" title="Remove" disabled={remove.isPending}
                                onClick={() => { if (confirm(`Remove ${m.email}? This deletes their account and data.`)) remove.mutate(m.membership_id) }}>
                                <Trash2 className="h-4 w-4 text-destructive" />
                              </Button>
                            </div>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
      {(patch.error || remove.error) && (
        <p className="text-sm text-destructive">{((patch.error || remove.error) as { error?: string })?.error ?? 'Action failed'}</p>
      )}
    </div>
  )
}
