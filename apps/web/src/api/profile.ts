import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'

export interface Fact {
  id: number
  category: string
  content: string
  source: 'ai_learned' | 'user_entered' | 'insight_confirmed'
  is_private: boolean
  created_at: string
  updated_at: string
}

export interface FactCategory {
  key: string
  label: string
  private_by_default: boolean
}

export type GoalStatus = 'active' | 'achieved' | 'dropped'

export interface Goal {
  id: number
  title: string
  why: string | null
  target_date: string | null
  board_id: number | null
  root_card_id: number | null
  status: GoalStatus
  created_by: string
}

const json = (body: unknown) => ({ body: JSON.stringify(body) })

export function useFacts() {
  return useQuery({
    queryKey: ['assistant', 'facts'],
    queryFn: () => api<{ categories: FactCategory[]; facts: Fact[] }>('/assistant/facts'),
  })
}

export function useFactMutations() {
  const qc = useQueryClient()
  const refresh = () => qc.invalidateQueries({ queryKey: ['assistant', 'facts'] })
  return {
    create: useMutation({
      mutationFn: (data: { category: string; content: string }) =>
        api<Fact>('/assistant/facts', { method: 'POST', ...json(data) }),
      onSuccess: refresh,
    }),
    update: useMutation({
      mutationFn: ({ id, ...data }: { id: number; content?: string; is_private?: boolean; category?: string }) =>
        api<Fact>(`/assistant/facts/${id}`, { method: 'PATCH', ...json(data) }),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (id: number) => api<void>(`/assistant/facts/${id}`, { method: 'DELETE' }),
      onSuccess: refresh,
    }),
  }
}

export function useGoals() {
  return useQuery({ queryKey: ['goals'], queryFn: () => api<Goal[]>('/goals') })
}

export function useGoalMutations() {
  const qc = useQueryClient()
  const refresh = () => qc.invalidateQueries({ queryKey: ['goals'] })
  return {
    create: useMutation({
      mutationFn: (data: { title: string; why?: string | null; target_date?: string | null; board_id?: number | null }) =>
        api<Goal>('/goals', { method: 'POST', ...json(data) }),
      onSuccess: refresh,
    }),
    update: useMutation({
      mutationFn: ({ id, ...data }: Partial<Goal> & { id: number }) =>
        api<Goal>(`/goals/${id}`, { method: 'PATCH', ...json(data) }),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (id: number) => api<void>(`/goals/${id}`, { method: 'DELETE' }),
      onSuccess: refresh,
    }),
  }
}
