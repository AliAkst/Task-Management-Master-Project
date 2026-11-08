import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import type { SessionManualCreate, TimeSession } from '../lib/types'

export const sessionKeys = {
  all: ['sessions'] as const,
  active: ['sessions', 'active'] as const,
  forCard: (cardId: number) => ['sessions', 'card', cardId] as const,
}

/** Calisan kronometre. Baska sekmede baslatilan/durdurulan da yakalansin diye periyodik. */
export function useActiveSession() {
  return useQuery({
    queryKey: sessionKeys.active,
    queryFn: () => api<{ session: TimeSession | null }>('/sessions/active').then((r) => r.session),
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  })
}

export function useCardSessions(cardId: number) {
  return useQuery({
    queryKey: sessionKeys.forCard(cardId),
    queryFn: () => api<TimeSession[]>(`/sessions?card_id=${cardId}`),
  })
}

/** Baslangictan bu yana gecen saniye; her saniye guncellenir. */
export function useElapsed(startedAt: string | null | undefined): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!startedAt) return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [startedAt])
  return startedAt ? Math.max(0, (now - new Date(startedAt).getTime()) / 1000) : 0
}

export function useSessionMutations() {
  const qc = useQueryClient()
  // Kart toplam sureleri board/kart sorgularinda; hepsini tazele
  const refresh = () => {
    qc.invalidateQueries({ queryKey: sessionKeys.all })
    qc.invalidateQueries({ queryKey: ['card'] })
    qc.invalidateQueries({ queryKey: ['board'] })
  }
  const json = (body: unknown) => ({ body: JSON.stringify(body) })

  return {
    start: useMutation({
      mutationFn: (cardId: number | null) =>
        api<TimeSession>('/sessions/start', { method: 'POST', ...json({ card_id: cardId }) }),
      onSuccess: (s) => {
        qc.setQueryData(sessionKeys.active, s)
        refresh()
      },
    }),
    stop: useMutation({
      mutationFn: () => api<TimeSession>('/sessions/stop', { method: 'POST', ...json({}) }),
      onSuccess: () => {
        qc.setQueryData(sessionKeys.active, null)
        refresh()
      },
      onError: refresh, // baska yerde durdurulmus olabilir
    }),
    createManual: useMutation({
      mutationFn: (data: SessionManualCreate) =>
        api<TimeSession>('/sessions', { method: 'POST', ...json(data) }),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (id: number) => api<void>(`/sessions/${id}`, { method: 'DELETE' }),
      onSuccess: refresh,
    }),
  }
}
