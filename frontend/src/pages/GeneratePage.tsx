import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import { useJobPolling } from '@/hooks/useJobPolling'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent } from '@/components/ui/card'
import { CheckCircle, Loader2 } from 'lucide-react'

const STEPS = ['researching', 'personalizing', 'scheduling', 'complete']
const STEP_LABELS: Record<string, string> = {
  researching: 'Researching prospect', personalizing: 'Writing outreach copy',
  scheduling: 'Recommending send time', complete: 'Done',
}

function OutreachStepper({ jobId, onReset }: { jobId: string; onReset: () => void }) {
  const navigate = useNavigate()
  const { data } = useJobPolling(jobId, (result) => {
    if (result.status === 'done') navigate(`/result/${jobId}`)
  })

  const currentStep = data?.current_step ?? null
  const failed = data?.status === 'failed'

  return (
    <Card className="mt-6"><CardContent className="pt-6 space-y-4">
      <div className="space-y-3">
        {STEPS.map(step => {
          const idx = STEPS.indexOf(step)
          const currentIdx = currentStep ? STEPS.indexOf(currentStep) : -1
          const done = currentIdx > idx || currentStep === 'complete'
          const active = currentStep === step
          return (
            <div key={step} className="flex items-center gap-3">
              {done ? <CheckCircle className="h-5 w-5 text-green-500" /> :
               active ? <Loader2 className="h-5 w-5 text-primary animate-spin" /> :
               <div className="h-5 w-5 rounded-full border-2 border-muted-foreground/30" />}
              <span className={active ? 'font-medium' : done ? 'text-muted-foreground' : 'text-muted-foreground/50'}>
                {STEP_LABELS[step]}
              </span>
            </div>
          )
        })}
      </div>
      {failed && (
        <div className="flex items-center justify-between gap-4">
          <p className="text-sm text-destructive">Job failed. <Link to={`/result/${jobId}`} className="underline">View details</Link></p>
          <Button size="sm" variant="outline" onClick={onReset}>Try again</Button>
        </div>
      )}
    </CardContent></Card>
  )
}

export function GeneratePage() {
  const [company, setCompany] = useState('')
  const [contact, setContact] = useState('')
  const [jobId, setJobId] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: () => apiFetch<{ job_id: string }>('/outreach/generate', {
      method: 'POST', body: JSON.stringify({ company_name: company, contact_name: contact || undefined }),
    }),
    onSuccess: (data) => setJobId(data.job_id),
  })

  return (
    <div className="max-w-xl">
      <h1 className="text-2xl font-bold mb-1">Generate outreach</h1>
      <p className="text-muted-foreground mb-6">Enter the prospect's company and we'll research, personalise, and schedule outreach for you.</p>
      <Card><CardContent className="pt-6">
        <form onSubmit={e => { e.preventDefault(); mutation.mutate() }} className="space-y-4">
          <div className="space-y-1"><Label>Company name *</Label><Input value={company} onChange={e => setCompany(e.target.value)} placeholder="Acme Corp" required disabled={!!jobId} /></div>
          <div className="space-y-1"><Label>Contact name <span className="text-muted-foreground">(optional)</span></Label><Input value={contact} onChange={e => setContact(e.target.value)} placeholder="Jane Smith" disabled={!!jobId} /></div>
          {mutation.error && <p className="text-sm text-destructive">{(mutation.error as { error?: string })?.error ?? 'Failed to start'}</p>}
          <Button type="submit" className="w-full" disabled={mutation.isPending || !!jobId}>
            {mutation.isPending ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Starting...</> : jobId ? 'Generating…' : 'Generate outreach'}
          </Button>
        </form>
      </CardContent></Card>
      {jobId && <OutreachStepper jobId={jobId} onReset={() => { setJobId(null); mutation.reset() }} />}
    </div>
  )
}
