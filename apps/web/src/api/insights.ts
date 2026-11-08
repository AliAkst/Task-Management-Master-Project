import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import type { DayReviewJob } from './assistant'

export interface Insight {
  id: number
  category: string
  observation: string
  evidence: Record<string, unknown> & { data_text?: string }
  status: 'new' | 'confirmed' | 'rejected'
  user_feedback: string | null
  fact_id: number | null
  created_at: string
  decided_at: string | null
}

/** Haftalik analiz isi: gun sonu isiyle ayni kayit, sonucu farkli. */
export type WeeklyJob = Omit<DayReviewJob, 'result'> & {
  result: {
    week_summary: string | null
    insight_ids: number[]
    period_start: string
    period_end: string
    notes: string[]
  } | null
}

const key = ['assistant', 'insights'] as const
const active = (j: WeeklyJob | null | undefined) => j?.status === 'queued' || j?.status === 'running'

export function useInsights() {
  return useQuery({
    queryKey: key,
    queryFn: () => api<{ job: WeeklyJob | null; items: Insight[] }>('/assistant/insights'),
    refetchInterval: (q) => (active(q.state.data?.job) ? 5000 : false),
  })
}

export function useInsightActions() {
  const qc = useQueryClient()
  const refresh = () => {
    qc.invalidateQueries({ queryKey: key })
    qc.invalidateQueries({ queryKey: ['assistant', 'facts'] })
  }
  return {
    analyze: useMutation({
      mutationFn: (day: string) => api<WeeklyJob>(`/assistant/insights/analyze?day=${day}`, { method: 'POST' }),
      onSuccess: refresh,
    }),
    confirm: useMutation({
      mutationFn: ({ id, content }: { id: number; content?: string }) =>
        api<Insight>(`/assistant/insights/${id}/confirm`, { method: 'POST', body: JSON.stringify({ content: content ?? null }) }),
      onSuccess: refresh,
    }),
    reject: useMutation({
      mutationFn: ({ id, reason }: { id: number; reason: string | null }) =>
        api<Insight>(`/assistant/insights/${id}/reject`, { method: 'POST', body: JSON.stringify({ reason }) }),
      onSuccess: refresh,
    }),
  }
}
