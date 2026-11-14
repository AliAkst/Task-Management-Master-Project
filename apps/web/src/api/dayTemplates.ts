import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import type { components } from '../lib/api-schema'
import { dayKeys } from './dayPlans'

type S = components['schemas']

export type TemplateBlock = S['TemplateBlock']
export type DayTemplate = Required<S['DayTemplateResponse']>
export type DayTemplateInput = S['DayTemplateCreate']
export type DayTemplateForDay = {
  template: DayTemplate | null
  source: 'off' | 'override' | 'weekday' | null
  applied_at: string | null
}
export type ApplyResult = { added: number; reason: 'applied' | 'no_template' | 'already_applied' }
export type TemplateMode = { mode: 'auto' | 'off' | 'template'; template_id?: number }

export const templateKeys = {
  all: ['day-templates'] as const,
  forDay: (day: string) => ['day', day, 'template'] as const,
}

const json = (body: unknown) => ({ body: JSON.stringify(body) })

export function useDayTemplates() {
  return useQuery({ queryKey: templateKeys.all, queryFn: () => api<DayTemplate[]>('/day-templates') })
}

export function useDayTemplateMutations() {
  const qc = useQueryClient()
  const refresh = () => {
    qc.invalidateQueries({ queryKey: templateKeys.all })
    qc.invalidateQueries({ queryKey: dayKeys.all })
  }
  return {
    create: useMutation({
      mutationFn: (body: DayTemplateInput) => api<DayTemplate>('/day-templates', { method: 'POST', ...json(body) }),
      onSuccess: refresh,
    }),
    update: useMutation({
      mutationFn: ({ id, body }: { id: number; body: Partial<DayTemplateInput> }) =>
        api<DayTemplate>(`/day-templates/${id}`, { method: 'PATCH', ...json(body) }),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (id: number) => api<void>(`/day-templates/${id}`, { method: 'DELETE' }),
      onSuccess: refresh,
    }),
  }
}

/** Gunun cozumlenen sablonu (off > gun secimi > hafta gunu). */
export function useDayTemplate(day: string) {
  return useQuery({
    queryKey: templateKeys.forDay(day),
    queryFn: () => api<DayTemplateForDay>(`/day-plans/${day}/template`),
  })
}

export function useDayTemplateDayMutations(day: string) {
  const qc = useQueryClient()
  return {
    setMode: useMutation({
      mutationFn: (body: TemplateMode) =>
        api<DayTemplateForDay>(`/day-plans/${day}/template`, { method: 'PUT', ...json(body) }),
      onSettled: () => qc.invalidateQueries({ queryKey: dayKeys.all }),
    }),
    apply: useMutation({
      mutationFn: () => api<ApplyResult>(`/day-plans/${day}/apply-template`, { method: 'POST', ...json({}) }),
      onSettled: () => qc.invalidateQueries({ queryKey: dayKeys.all }),
    }),
  }
}
