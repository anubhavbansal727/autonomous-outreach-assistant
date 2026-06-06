import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import { useBatchPolling } from '@/hooks/useBatchPolling'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Loader2, Upload, Download, AlertCircle } from 'lucide-react'
import type { BatchCreateResponse, BatchProspectStatus } from '@/types'

const MAX_PROSPECTS = 20
const SAMPLE_CSV = 'company_name,contact_name\nAcme Corp,Jane Smith\nGlobex,John Doe\n'

interface Preview {
  rows: { company_name: string; contact_name: string }[]
  error: string | null
}

// Light client-side parse for preview only — the backend is the source of truth.
function parseCsvPreview(text: string): Preview {
  const lines = text.split(/\r?\n/).filter((l) => l.trim() !== '')
  if (lines.length === 0) return { rows: [], error: 'File is empty.' }
  const header = lines[0].split(',').map((h) => h.trim().toLowerCase())
  const companyIdx = header.indexOf('company_name')
  const contactIdx = header.indexOf('contact_name')
  if (companyIdx === -1) return { rows: [], error: "CSV must have a 'company_name' column." }
  const rows = lines.slice(1).map((line) => {
    const cols = line.split(',')
    return {
      company_name: (cols[companyIdx] ?? '').trim(),
      contact_name: contactIdx === -1 ? '' : (cols[contactIdx] ?? '').trim(),
    }
  }).filter((r) => r.company_name !== '')
  if (rows.length === 0) return { rows: [], error: 'No prospect rows found.' }
  if (rows.length > MAX_PROSPECTS) return { rows, error: `Batch is limited to ${MAX_PROSPECTS} prospects (found ${rows.length}).` }
  return { rows, error: null }
}

function ProspectRow({ p, i }: { p: BatchProspectStatus; i: number }) {
  const stepLabel = p.status === 'failed' ? 'failed'
    : p.status === 'done' ? 'complete'
    : p.current_step ?? 'queued'
  const variant = p.status === 'done' ? 'success' : p.status === 'failed' ? 'destructive' : 'secondary'
  return (
    <tr className={`border-b last:border-0 ${i % 2 === 0 ? '' : 'bg-muted/10'}`}>
      <td className="px-4 py-2.5 font-medium">
        {p.status === 'done'
          ? <Link to={`/result/${p.job_id}`} className="text-primary hover:underline">{p.company_name}</Link>
          : p.company_name}
      </td>
      <td className="px-4 py-2.5 text-muted-foreground">{p.contact_name ?? '—'}</td>
      <td className="px-4 py-2.5">
        <Badge variant={variant as 'success' | 'destructive' | 'secondary'} className="capitalize">{stepLabel}</Badge>
      </td>
    </tr>
  )
}

function ProgressBar({ label, done, total }: { label: string; done: number; total: number }) {
  const pct = total > 0 ? Math.round((done / total) * 100) : 0
  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-sm">
        <span className="font-medium">{label}</span>
        <span className="text-muted-foreground">{done}/{total}</span>
      </div>
      <div className="h-2 rounded-full bg-muted overflow-hidden">
        <div className="h-full bg-primary transition-all duration-500" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function BatchProgress({ batchId }: { batchId: string }) {
  const { data } = useBatchPolling(batchId)
  if (!data) {
    return <Card className="mt-6"><CardContent className="flex items-center justify-center p-12"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></CardContent></Card>
  }
  return (
    <Card className="mt-6">
      <CardContent className="pt-6 space-y-5">
        <div className="space-y-4">
          <ProgressBar label="Research" done={data.research_done} total={data.total} />
          <ProgressBar label="Personalizing" done={data.personalize_done} total={data.total} />
        </div>
        <table className="w-full text-sm">
          <thead className="border-b"><tr className="text-left">
            {['Company', 'Contact', 'Stage'].map((h) => (
              <th key={h} className="px-4 py-2 font-medium text-muted-foreground">{h}</th>
            ))}
          </tr></thead>
          <tbody>
            {data.prospects.map((p, i) => <ProspectRow key={p.job_id} p={p} i={i} />)}
          </tbody>
        </table>
        {data.status === 'done' && (
          <p className="text-sm text-green-600 font-medium">Batch complete — click any company to review and send.</p>
        )}
        {data.status === 'failed' && (
          <p className="text-sm text-destructive">Batch failed. Some prospects may not have completed.</p>
        )}
      </CardContent>
    </Card>
  )
}

export function BatchPage() {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [batchId, setBatchId] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: async () => {
      const form = new FormData()
      form.append('file', file as File)
      return apiFetch<BatchCreateResponse>('/outreach/batch', { method: 'POST', body: form })
    },
    onSuccess: (data) => setBatchId(data.batch_id),
  })

  const handleFile = async (f: File | null) => {
    setFile(f)
    setPreview(f ? parseCsvPreview(await f.text()) : null)
  }

  const downloadSample = () => {
    const url = URL.createObjectURL(new Blob([SAMPLE_CSV], { type: 'text/csv' }))
    const a = document.createElement('a')
    a.href = url
    a.download = 'prospects_sample.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  const canSubmit = !!file && !!preview && !preview.error && !batchId

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold mb-1">Batch outreach</h1>
      <p className="text-muted-foreground mb-6">
        Upload a CSV of up to {MAX_PROSPECTS} prospects. We research them all in parallel, then write personalised outreach for each.
      </p>

      {!batchId && (
        <Card><CardContent className="pt-6 space-y-4">
          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 cursor-pointer text-sm font-medium text-primary hover:underline">
              <Upload className="h-4 w-4" />
              {file ? file.name : 'Choose CSV file'}
              <input type="file" accept=".csv,text/csv" className="hidden"
                onChange={(e) => handleFile(e.target.files?.[0] ?? null)} />
            </label>
            <Button variant="ghost" size="sm" onClick={downloadSample}>
              <Download className="mr-2 h-4 w-4" />Sample CSV
            </Button>
          </div>

          {preview?.error && (
            <p className="flex items-center gap-2 text-sm text-destructive"><AlertCircle className="h-4 w-4" />{preview.error}</p>
          )}

          {preview && !preview.error && (
            <div className="rounded-md border">
              <p className="px-4 py-2 text-sm text-muted-foreground border-b">{preview.rows.length} prospect{preview.rows.length === 1 ? '' : 's'} ready</p>
              <table className="w-full text-sm">
                <tbody>
                  {preview.rows.slice(0, 5).map((r, i) => (
                    <tr key={i} className="border-b last:border-0">
                      <td className="px-4 py-2 font-medium">{r.company_name}</td>
                      <td className="px-4 py-2 text-muted-foreground">{r.contact_name || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {preview.rows.length > 5 && <p className="px-4 py-2 text-xs text-muted-foreground">…and {preview.rows.length - 5} more</p>}
            </div>
          )}

          {mutation.error && (
            <p className="text-sm text-destructive">{(mutation.error as { error?: string })?.error ?? 'Failed to start batch'}</p>
          )}

          <Button className="w-full" disabled={!canSubmit || mutation.isPending} onClick={() => mutation.mutate()}>
            {mutation.isPending ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Starting…</> : 'Start batch'}
          </Button>
        </CardContent></Card>
      )}

      {batchId && <BatchProgress batchId={batchId} />}
    </div>
  )
}
