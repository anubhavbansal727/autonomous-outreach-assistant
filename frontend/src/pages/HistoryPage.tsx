import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { apiFetch } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { PERMISSIONS } from '@/lib/permissions'
import type { HistoryItem } from '@/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import { Loader2, ChevronLeft, ChevronRight } from 'lucide-react'

function StatusBadge({ status }: { status: string }) {
  const v = status === 'done' ? 'success' : status === 'failed' ? 'destructive' : 'secondary'
  return <Badge variant={v as 'success' | 'destructive' | 'secondary'} className="capitalize">{status}</Badge>
}

function SendBadge({ status }: { status: string }) {
  const v = status === 'sent' ? 'success' : status === 'draft' ? 'outline' : 'secondary'
  return <Badge variant={v as 'success' | 'outline' | 'secondary'} className="capitalize">{status}</Badge>
}

export function HistoryPage() {
  const navigate = useNavigate()
  const { can } = useAuth()
  const canViewAll = can(PERMISSIONS.OUTREACH_VIEW_ALL)
  const [page, setPage] = useState(1)
  const [scope, setScope] = useState<'mine' | 'all'>('mine')
  const perPage = 20

  const { data, isLoading } = useQuery<{ items: HistoryItem[]; total: number; page: number; per_page: number }>({
    queryKey: ['outreach', 'history', page, scope],
    queryFn: () => apiFetch(`/outreach/history?page=${page}&per_page=${perPage}&scope=${scope}`),
    staleTime: 60_000,
  })

  const totalPages = data ? Math.ceil(data.total / perPage) : 1

  const setScopeReset = (s: 'mine' | 'all') => { setScope(s); setPage(1) }

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-bold">History</h1>
        {canViewAll && (
          <div className="inline-flex rounded-md border p-0.5 text-sm">
            {(['mine', 'all'] as const).map(s => (
              <button key={s} onClick={() => setScopeReset(s)}
                className={cn('px-3 py-1 rounded capitalize transition-colors',
                  scope === s ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground')}>
                {s === 'mine' ? 'My outreach' : 'All members'}
              </button>
            ))}
          </div>
        )}
      </div>
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex items-center justify-center p-12"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
          ) : !data?.items.length ? (
            <div className="text-center p-12 text-muted-foreground">No outreach jobs yet. <Link to="/generate" className="text-primary hover:underline">Generate your first one.</Link></div>
          ) : (
            <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b"><tr className="text-left">
                {['Company', 'Contact', 'Status', 'Send status', 'Confidence', 'Created'].map(h => (
                  <th key={h} className="px-4 py-3 font-medium text-muted-foreground">{h}</th>
                ))}
              </tr></thead>
              <tbody>
                {data.items.map((item, i) => (
                  <tr key={item.id} onClick={() => navigate(`/result/${item.id}`)}
                    className={`border-b last:border-0 hover:bg-muted/30 cursor-pointer ${i % 2 === 0 ? '' : 'bg-muted/10'}`}>
                    <td className="px-4 py-3"><Link to={`/result/${item.id}`} className="text-primary hover:underline font-medium">{item.company_name}</Link></td>
                    <td className="px-4 py-3 text-muted-foreground">{item.contact_name ?? '—'}</td>
                    <td className="px-4 py-3"><StatusBadge status={item.status} /></td>
                    <td className="px-4 py-3"><SendBadge status={item.send_status} /></td>
                    <td className="px-4 py-3 capitalize text-muted-foreground">{item.data_confidence ?? '—'}</td>
                    <td className="px-4 py-3 text-muted-foreground">{new Date(item.created_at).toLocaleDateString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          )}
        </CardContent>
      </Card>
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">Page {page} of {totalPages} &middot; {data?.total ?? 0} total</p>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}><ChevronLeft className="h-4 w-4" /></Button>
            <Button variant="outline" size="sm" onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}><ChevronRight className="h-4 w-4" /></Button>
          </div>
        </div>
      )}
    </div>
  )
}
