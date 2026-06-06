import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import type { BatchStatusResponse } from '@/types'

export function useBatchPolling(batchId: string | null) {
  return useQuery<BatchStatusResponse>({
    queryKey: ['outreach', 'batch', batchId],
    queryFn: () => apiFetch<BatchStatusResponse>(`/outreach/batch/${batchId}`),
    enabled: !!batchId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'done' || status === 'failed' ? false : 3000
    },
  })
}
