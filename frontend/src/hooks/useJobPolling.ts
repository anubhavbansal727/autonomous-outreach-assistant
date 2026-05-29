import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import type { JobStatusResponse } from '@/types'

export function useJobPolling(jobId: string | null, onComplete?: (status: JobStatusResponse) => void) {
  return useQuery<JobStatusResponse>({
    queryKey: ['outreach', 'status', jobId],
    queryFn: () => apiFetch<JobStatusResponse>(`/outreach/status/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (status === 'done' || status === 'failed') {
        if (query.state.data && onComplete) onComplete(query.state.data)
        return false
      }
      return 3000
    },
  })
}

export function useIngestionPolling(jobId: string | null) {
  return useQuery({
    queryKey: ['ingestion', 'status', jobId],
    queryFn: () => apiFetch<{ job_id: string; status: string; current_step: string | null; profile: Record<string, unknown> | null; error_message: string | null }>(`/profile/result/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'done' || status === 'failed' ? false : 3000
    },
  })
}
