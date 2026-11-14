import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../lib/api'
import type { Course } from '../lib/types'
import { sessionKeys } from './sessions'

export const courseKeys = {
  all: ['learning', 'courses'] as const,
  list: (include: 'active' | 'all') => ['learning', 'courses', include] as const,
}

const json = (body: unknown) => ({ body: JSON.stringify(body) })

/** Satirda gosterilecek hata: sunucu mesaji (409 / 422) ya da ag hatasi. */
export function courseErrorText(err: unknown): string {
  return err instanceof ApiError ? err.message : 'Ulaşılamadı'
}

export function useCourses(include: 'active' | 'all' = 'active') {
  return useQuery({
    queryKey: courseKeys.list(include),
    queryFn: () => api<Course[]>(`/learning/courses?include=${include}`),
  })
}

export function useCourseMutations() {
  const qc = useQueryClient()
  const refresh = () => {
    qc.invalidateQueries({ queryKey: courseKeys.all })
    qc.invalidateQueries({ queryKey: sessionKeys.active })
  }
  return {
    /** Duraklat / Aktif et (3. aktif kurs sunucuda 409). */
    setStatus: useMutation({
      mutationFn: ({ goalId, status }: { goalId: number; status: 'active' | 'paused' }) =>
        api(`/goals/${goalId}`, { method: 'PATCH', ...json({ status }) }),
      onSuccess: refresh,
    }),
    /** Alt parcalari olan karti kurs olarak takibe al. */
    track: useMutation({
      mutationFn: (rootCardId: number) =>
        api<Course>('/learning/courses', { method: 'POST', ...json({ root_card_id: rootCardId }) }),
      onSuccess: refresh,
    }),
  }
}
