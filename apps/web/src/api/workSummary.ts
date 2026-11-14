import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import type { components } from '../lib/api-schema'

export type WorkSummary = components['schemas']['WorkSummary']

/** Bir gunun Markdown is ozeti (Faz 13h1). boardIds null/bos = tum board'lar. */
export function useWorkSummary(day: string, boardIds: number[] | null) {
  const ids = boardIds && boardIds.length ? boardIds.join(',') : null
  return useQuery({
    queryKey: ['work-summary', day, ids],
    queryFn: () =>
      api<WorkSummary>(`/reports/work-summary?date=${day}${ids ? `&board_ids=${ids}` : ''}`),
  })
}
