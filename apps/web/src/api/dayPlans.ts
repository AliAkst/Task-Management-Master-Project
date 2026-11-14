import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import type { AnalyticsSummary, DayPlan, DayPlanItemPatch, DayReview, ItemMove, ItemToCard, PlanItemInput, PlanSuggestion } from '../lib/types'

export const dayKeys = {
  all: ['day'] as const,
  plan: (day: string) => ['day', day, 'plan'] as const,
  suggestions: (day: string) => ['day', day, 'suggestions'] as const,
  analytics: (start: string, end: string) => ['analytics', start, end] as const,
}

/** Tarayicinin yerel gunu "YYYY-MM-DD" (kullanicinin saat dilimi ile ayni varsayilir). */
export function localDay(d = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function shiftDay(day: string, delta: number): string {
  const [y, m, d] = day.split('-').map(Number)
  return localDay(new Date(y, m - 1, d + delta))
}

export function useDayPlan(day: string) {
  return useQuery({ queryKey: dayKeys.plan(day), queryFn: () => api<DayPlan>(`/day-plans/${day}`) })
}

export function useSuggestions(day: string) {
  return useQuery({
    queryKey: dayKeys.suggestions(day),
    queryFn: () =>
      api<{ items: PlanSuggestion[] }>(`/day-plans/${day}/suggestions`).then((r) => r.items),
  })
}

export function useAnalytics(start: string, end: string) {
  return useQuery({
    queryKey: dayKeys.analytics(start, end),
    queryFn: () => api<AnalyticsSummary>(`/analytics/summary?start=${start}&end=${end}`),
  })
}

export function useDayPlanMutations(day: string) {
  const qc = useQueryClient()
  const refresh = () => {
    qc.invalidateQueries({ queryKey: dayKeys.all })
    qc.invalidateQueries({ queryKey: ['analytics'] })
    // Degerlendirme kartlari tamamlayabilir -> kanban/kart verisi de tazelensin
    qc.invalidateQueries({ queryKey: ['board'] })
    qc.invalidateQueries({ queryKey: ['boards'] })
    qc.invalidateQueries({ queryKey: ['card'] })
  }
  const json = (body: unknown) => ({ body: JSON.stringify(body) })
  return {
    save: useMutation({
      mutationFn: (items: PlanItemInput[]) =>
        api<DayPlan>(`/day-plans/${day}`, { method: 'PUT', ...json({ items }) }),
      onSuccess: (plan) => {
        qc.setQueryData(dayKeys.plan(day), plan)
        refresh()
      },
    }),
    patchItem: useMutation({
      mutationFn: ({ id, body }: { id: number; body: DayPlanItemPatch }) =>
        api<DayPlan>(`/day-plan-items/${id}`, { method: 'PATCH', ...json(body) }),
      onSuccess: (plan) => {
        qc.setQueryData(dayKeys.plan(plan.date), plan)
        refresh()
      },
    }),
    toCard: useMutation({
      mutationFn: ({ id, body }: { id: number; body: ItemToCard }) =>
        api<DayPlan>(`/day-plan-items/${id}/to-card`, { method: 'POST', ...json(body) }),
      onSuccess: (plan) => {
        qc.setQueryData(dayKeys.plan(plan.date), plan)
        refresh()
      },
    }),
    moveItem: useMutation({
      mutationFn: ({ id, body }: { id: number; body: ItemMove }) =>
        api<DayPlan>(`/day-plan-items/${id}/move`, { method: 'POST', ...json(body) }),
      onSuccess: (plan) => {
        qc.setQueryData(dayKeys.plan(plan.date), plan)
        refresh()
      },
    }),
    review: useMutation({
      mutationFn: (data: DayReview) =>
        api<DayPlan>(`/day-plans/${day}/review`, { method: 'POST', ...json(data) }),
      onSuccess: (plan) => {
        qc.setQueryData(dayKeys.plan(day), plan)
        refresh()
      },
    }),
  }
}
