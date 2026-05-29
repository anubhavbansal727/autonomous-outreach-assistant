import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch } from '@/api/client'
import { useIngestionPolling } from '@/hooks/useJobPolling'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { CheckCircle, Loader2, AlertCircle } from 'lucide-react'

type Phase = 'url' | 'progress' | 'review'

interface ProfileDraft {
  product_name: string
  one_liner: string
  target_customer: string
  pain_points: string[]
  differentiators: string[]
  case_studies: string[]
  cta: string
  icp: string
  avoid_messaging: string
  source_url: string
}

const STEPS = ['scraping', 'extracting', 'complete']
const STEP_LABELS: Record<string, string> = { scraping: 'Scraping website', extracting: 'Extracting profile', complete: 'Done' }

function StepIndicator({ currentStep }: { currentStep: string | null }) {
  return (
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
            <span className={active ? 'font-medium text-foreground' : done ? 'text-muted-foreground' : 'text-muted-foreground/50'}>
              {STEP_LABELS[step]}
            </span>
          </div>
        )
      })}
    </div>
  )
}

function FieldArrayEditor({ label, values, onChange }: { label: string; values: string[]; onChange: (v: string[]) => void }) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      {values.map((v, i) => (
        <div key={i} className="flex gap-2">
          <Input value={v} onChange={e => { const n = [...values]; n[i] = e.target.value; onChange(n) }} />
          <Button type="button" variant="outline" size="sm" onClick={() => onChange(values.filter((_, j) => j !== i))}>x</Button>
        </div>
      ))}
      <Button type="button" variant="outline" size="sm" onClick={() => onChange([...values, ''])}>+ Add</Button>
    </div>
  )
}

export function OnboardingPage() {
  const navigate = useNavigate()
  const [phase, setPhase] = useState<Phase>('url')
  const [url, setUrl] = useState('')
  const [jobId, setJobId] = useState<string | null>(null)
  const [urlError, setUrlError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [savingProfile, setSavingProfile] = useState(false)
  const [profileLoaded, setProfileLoaded] = useState(false)
  const [draft, setDraft] = useState<ProfileDraft>({
    product_name: '', one_liner: '', target_customer: '',
    pain_points: [], differentiators: [], case_studies: [],
    cta: '', icp: '', avoid_messaging: '', source_url: '',
  })

  const pollingResult = useIngestionPolling(phase === 'progress' ? jobId : null)

  // Transition from progress -> review when done
  if (phase === 'progress' && pollingResult.data?.status === 'done' && pollingResult.data.profile && !profileLoaded) {
    const p = pollingResult.data.profile as Record<string, unknown>
    const next: ProfileDraft = {
      product_name: (p.product_name as string) ?? '',
      one_liner: (p.one_liner as string) ?? '',
      target_customer: (p.target_customer as string) ?? '',
      pain_points: (p.pain_points as string[]) ?? [],
      differentiators: (p.differentiators as string[]) ?? [],
      case_studies: (p.case_studies as string[]) ?? [],
      cta: (p.cta as string) ?? '',
      icp: (p.icp as string) ?? '',
      avoid_messaging: '',
      source_url: url,
    }
    setDraft(next)
    setProfileLoaded(true)
    setPhase('review')
  }

  const handleStartIngest = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      setUrlError('URL must start with http:// or https://'); return
    }
    setUrlError(''); setSubmitting(true)
    try {
      const data = await apiFetch<{ job_id: string }>('/profile/ingest', { method: 'POST', body: JSON.stringify({ url }) })
      setJobId(data.job_id)
      setPhase('progress')
    } catch (err: unknown) {
      setUrlError((err as { error?: string })?.error ?? 'Failed to start ingestion')
    } finally { setSubmitting(false) }
  }

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault()
    setSavingProfile(true)
    try {
      await apiFetch('/profile/save', { method: 'POST', body: JSON.stringify(draft) })
      navigate('/generate')
    } catch (err: unknown) {
      alert((err as { error?: string })?.error ?? 'Failed to save profile')
    } finally { setSavingProfile(false) }
  }

  if (phase === 'url') return (
    <div className="max-w-xl">
      <h1 className="text-2xl font-bold mb-1">Welcome! Let's set up your product profile</h1>
      <p className="text-muted-foreground mb-6">Enter your product URL and our AI will scrape and extract your positioning automatically.</p>
      <Card><CardContent className="pt-6">
        <form onSubmit={handleStartIngest} className="space-y-4">
          <div className="space-y-1">
            <Label>Product website URL</Label>
            <Input value={url} onChange={e => setUrl(e.target.value)} placeholder="https://yourproduct.com" required />
            {urlError && <p className="text-sm text-destructive">{urlError}</p>}
          </div>
          <Button type="submit" className="w-full" disabled={submitting}>
            {submitting ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Starting...</> : 'Analyze my product'}
          </Button>
        </form>
      </CardContent></Card>
    </div>
  )

  if (phase === 'progress') {
    const data = pollingResult.data
    const failed = data?.status === 'failed'
    return (
      <div className="max-w-md">
        <h1 className="text-2xl font-bold mb-1">Analyzing your website</h1>
        <p className="text-muted-foreground mb-6">This takes about 30-60 seconds.</p>
        <Card><CardContent className="pt-6 space-y-6">
          <StepIndicator currentStep={data?.current_step ?? null} />
          {failed && (
            <div className="flex items-start gap-2 text-destructive text-sm">
              <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
              <span>{data?.error_message ?? 'Ingestion failed. Please try again.'}</span>
            </div>
          )}
          {failed && <Button variant="outline" onClick={() => { setPhase('url'); setJobId(null) }}>Try again</Button>}
        </CardContent></Card>
      </div>
    )
  }

  // Review phase
  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold mb-1">Review your product profile</h1>
      <p className="text-muted-foreground mb-6">Our AI pre-filled this from your website. Edit anything before saving.</p>
      <form onSubmit={handleSaveProfile} className="space-y-6">
        <Card><CardContent className="pt-6 space-y-4">
          <div className="space-y-1"><Label>Product name *</Label><Input value={draft.product_name} onChange={e => setDraft(d => ({ ...d, product_name: e.target.value }))} required /></div>
          <div className="space-y-1"><Label>One-liner value prop</Label><Input value={draft.one_liner} onChange={e => setDraft(d => ({ ...d, one_liner: e.target.value }))} /></div>
          <div className="space-y-1"><Label>Target customer</Label><Input value={draft.target_customer} onChange={e => setDraft(d => ({ ...d, target_customer: e.target.value }))} /></div>
          <div className="space-y-1"><Label>Call to action</Label><Input value={draft.cta} onChange={e => setDraft(d => ({ ...d, cta: e.target.value }))} /></div>
          <div className="space-y-1"><Label>Ideal customer profile (ICP)</Label><Textarea value={draft.icp} onChange={e => setDraft(d => ({ ...d, icp: e.target.value }))} rows={2} /></div>
          <FieldArrayEditor label="Pain points" values={draft.pain_points} onChange={v => setDraft(d => ({ ...d, pain_points: v }))} />
          <FieldArrayEditor label="Differentiators" values={draft.differentiators} onChange={v => setDraft(d => ({ ...d, differentiators: v }))} />
          <FieldArrayEditor label="Case studies" values={draft.case_studies} onChange={v => setDraft(d => ({ ...d, case_studies: v }))} />
          <div className="space-y-1">
            <Label>Topics to avoid in outreach <Badge variant="warning" className="ml-2">Never AI-inferred</Badge></Label>
            <Textarea value={draft.avoid_messaging} onChange={e => setDraft(d => ({ ...d, avoid_messaging: e.target.value }))} placeholder="e.g. pricing comparisons, competitor names..." rows={2} />
          </div>
        </CardContent></Card>
        <Button type="submit" className="w-full" disabled={savingProfile}>{savingProfile ? 'Saving...' : 'Save profile & continue'}</Button>
      </form>
    </div>
  )
}
