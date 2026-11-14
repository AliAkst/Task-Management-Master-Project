import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import type { components } from '../lib/api-schema'
import { keys } from './boards'

type S = components['schemas']
export type SweepCard = S['SweepCard']
export type SweepGroup = S['SweepGroup']
export type SweepCandidates = S['SweepCandidates']
export type BulkOp = 'archive' | 'unarchive' | 'complete' | 'move'

export const sweepKey = (boardId: number) => ['sweep', boardId] as const

export function useSweepCandidates(boardId: number) {
  return useQuery({
    queryKey: sweepKey(boardId),
    queryFn: () => api<SweepCandidates>(`/boards/${boardId}/sweep-candidates`),
    staleTime: 0,
  })
}

/** Toplu islem (en fazla 200 kart). Cagiran parcalara boler. */
export function useBulkCards(boardId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { ids: number[]; op: BulkOp }) =>
      api<{ updated: number }>('/cards/bulk', { method: 'POST', body: JSON.stringify(v) }),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: keys.board(boardId) })
      qc.invalidateQueries({ queryKey: keys.boards })
      qc.invalidateQueries({ queryKey: sweepKey(boardId) })
    },
  })
}
