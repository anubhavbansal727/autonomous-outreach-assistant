import { useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { PERMISSIONS } from '@/lib/permissions'
import type { OutreachJob } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { AlertCircle, Edit2, Send, RefreshCw, Calendar, Loader2, ArrowLeft } from 'lucide-react'

function ConfidenceBadge({ level }: { level: string | null }) {
  if (!level) return null
  const variants = { high: 'success', medium: 'warning', low: 'destructive' } as const
  return <Badge variant={variants[level as keyof typeof variants] ?? 'outline'} className="capitalize">{level} confidence</Badge>
}

function SendDialog({ jobId, disabled }: { jobId: string; disabled: boolean }) {
  const [open, setOpen] = useState(false)
  const [email, setEmail] = useState('')
  const [sending, setSending] = useState(false)
  const [err, setErr] = useState('')
  const qc = useQueryClient()

  const handleSend = async () => {
    setSending(true); setErr('')
    try {
      await apiFetch(`/outreach/send/${jobId}`, { method: 'POST', body: JSON.stringify({ to_email: email }) })
      qc.invalidateQueries({ queryKey: ['outreach', 'result', jobId] })
      setOpen(false)
    } catch (e: unknown) { setErr((e as { error?: string })?.error ?? 'Send failed') }
    finally { setSending(false) }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button disabled={disabled} className="gap-2"><Send className="h-4 w-4" />Approve & Send</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Send outreach email</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1"><Label>Recipient email address</Label><Input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="prospect@company.com" /></div>
          {err && <p className="text-sm text-destructive">{err}</p>}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={handleSend} disabled={!email || sending}>{sending ? 'Sending...' : 'Send email'}</Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export function ResultPage() {
  const { jobId } = useParams<{ jobId: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { user, can } = useAuth()
  const [editMode, setEditMode] = useState(false)
  const [editValues, setEditValues] = useState({ email_subject: '', email_draft: '', linkedin_draft: '' })

  const { data: job, isLoading, error } = useQuery<OutreachJob>({
    queryKey: ['outreach', 'result', jobId],
    queryFn: () => apiFetch<OutreachJob>(`/outreach/result/${jobId}`),
    enabled: !!jobId,
    staleTime: 30_000,
  })

  const editMutation = useMutation({
    mutationFn: (payload: typeof editValues) => apiFetch(`/outreach/result/${jobId}`, { method: 'PUT', body: JSON.stringify(payload) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['outreach', 'result', jobId] }); setEditMode(false) },
  })

  const retryMutation = useMutation({
    mutationFn: () => apiFetch(`/outreach/retry/${jobId}`, { method: 'POST' }),
    onSuccess: () => navigate('/generate'),
  })

  if (isLoading) return <div className="flex items-center gap-2 text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />Loading result...</div>
  if (error) return <p className="text-destructive">Failed to load result.</p>
  if (!job) return null

  const enterEdit = () => {
    setEditValues({ email_subject: job.email_subject ?? '', email_draft: job.email_draft ?? '', linkedin_draft: job.linkedin_draft ?? '' })
    setEditMode(true)
  }

  const alreadySent = job.send_status === 'sent'
  const schedule = job.schedule_json
  // Edit/send/retry are owner-only (an admin viewing via outreach.view.all sees
  // a read-only copy). The server enforces this too — this just hides dead buttons.
  const isOwner = job.user_id === user?.id
  const canEdit = isOwner && can(PERMISSIONS.OUTREACH_CREATE)
  const canSend = isOwner && can(PERMISSIONS.OUTREACH_SEND)

  return (
    <div className="max-w-2xl space-y-6">
      <Link to="/history" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors">
        <ArrowLeft className="h-4 w-4" />Back to history
      </Link>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold break-words">{job.company_name}</h1>
          {job.contact_name && <p className="text-muted-foreground">{job.contact_name}</p>}
        </div>
        <ConfidenceBadge level={job.data_confidence} />
      </div>

      {job.status === 'failed' && (
        <div className="flex flex-wrap items-start gap-2 p-4 rounded-md bg-destructive/10 text-destructive text-sm">
          <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
          <div className="min-w-0 flex-1 basis-48"><p className="font-medium">Job failed</p><p className="break-words">{job.error_message}</p></div>
          {canEdit && (
            <Button size="sm" variant="outline" className="ml-auto shrink-0" onClick={() => retryMutation.mutate()} disabled={retryMutation.isPending}>
              <RefreshCw className="h-3 w-3 mr-1" />Retry
            </Button>
          )}
        </div>
      )}

      {/* Email card */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-base">Email</CardTitle>
          {!alreadySent && !editMode && canEdit && <Button size="sm" variant="outline" onClick={enterEdit}><Edit2 className="h-3 w-3 mr-1" />Edit</Button>}
          {alreadySent && <Badge variant="success">Sent</Badge>}
        </CardHeader>
        <CardContent className="space-y-4">
          {editMode ? (
            <>
              <div className="space-y-1"><Label>Subject</Label><Input value={editValues.email_subject} onChange={e => setEditValues(v => ({ ...v, email_subject: e.target.value }))} /></div>
              <div className="space-y-1"><Label>Body</Label><Textarea value={editValues.email_draft} onChange={e => setEditValues(v => ({ ...v, email_draft: e.target.value }))} rows={10} /></div>
              <div className="flex gap-2">
                <Button onClick={() => editMutation.mutate(editValues)} disabled={editMutation.isPending}>Save changes</Button>
                <Button variant="outline" onClick={() => setEditMode(false)}>Cancel</Button>
              </div>
            </>
          ) : (
            <>
              <div><p className="text-xs text-muted-foreground mb-1">Subject</p><p className="font-medium">{job.email_subject ?? '—'}</p></div>
              <div><p className="text-xs text-muted-foreground mb-1">Body</p><pre className="whitespace-pre-wrap break-words text-sm font-sans leading-relaxed">{job.email_draft ?? '—'}</pre></div>
              {canSend
                ? <SendDialog jobId={job.id} disabled={alreadySent || job.status !== 'done'} />
                : !isOwner && <p className="text-xs text-muted-foreground">Read-only — this outreach belongs to another member.</p>}
            </>
          )}
        </CardContent>
      </Card>

      {/* LinkedIn card */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-base">LinkedIn note</CardTitle>
          {editMode && <span className="text-xs text-muted-foreground">{editValues.linkedin_draft.length}/300</span>}
        </CardHeader>
        <CardContent>
          {editMode ? (
            <Textarea value={editValues.linkedin_draft} onChange={e => setEditValues(v => ({ ...v, linkedin_draft: e.target.value.slice(0, 300) }))} rows={3} />
          ) : (
            <p className="text-sm">{job.linkedin_draft ?? '—'}</p>
          )}
        </CardContent>
      </Card>

      {/* Schedule card */}
      {schedule && (
        <Card>
          <CardHeader><CardTitle className="text-base flex items-center gap-2"><Calendar className="h-4 w-4" />Scheduling recommendation</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {schedule.flag_for_human && (
              <div className="flex items-start gap-2 p-3 rounded-md bg-amber-50 border border-amber-200 text-amber-800 text-sm">
                <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                <span><strong>Review before sending.</strong> {schedule.reason}</span>
              </div>
            )}
            <div className="flex flex-wrap items-center gap-4 text-sm">
              <div><p className="text-xs text-muted-foreground">Recommended window</p><p className="font-medium">{schedule.recommended_window}</p></div>
              <div><p className="text-xs text-muted-foreground">Channel</p><p className="font-medium capitalize">{schedule.channel}</p></div>
            </div>
            {!schedule.flag_for_human && <p className="text-xs text-muted-foreground">{schedule.reason}</p>}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
