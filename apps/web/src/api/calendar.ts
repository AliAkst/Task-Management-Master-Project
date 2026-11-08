import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import type { CalendarEvent, CalendarItem, EventCreate, EventUpdate } from '../lib/types'

export const calendarKeys = {
  all: ['calendar'] as const,
  range: (start: string, end: string, boards: number[]) =>
    ['calendar', start, end, boards.join(',')] as const,
  cardEvents: (cardId: number) => ['card', cardId, 'events'] as const,
}

export function useCalendar(start: string | null, end: string | null, boardIds: number[]) {
  return useQuery({
    queryKey: calendarKeys.range(start ?? '', end ?? '', boardIds),
    queryFn: () => {
      const q = new URLSearchParams({ start: start!, end: end! })
      boardIds.forEach((id) => q.append('board_id', String(id)))
      return api<{ items: CalendarItem[] }>(`/calendar?${q}`).then((r) => r.items)
    },
    enabled: !!start && !!end,
    placeholderData: (prev) => prev, // hafta degistirirken takvim bosalmasin
  })
}

export function useCardEvents(cardId: number | null) {
  return useQuery({
    queryKey: calendarKeys.cardEvents(cardId ?? 0),
    queryFn: () => api<CalendarEvent[]>(`/cards/${cardId}/events`),
    enabled: cardId !== null,
  })
}

/** Etkinlik ve kart son tarihi degisiklikleri; hepsi takvimi ve kart verisini tazeler. */
export function useCalendarMutations() {
  const qc = useQueryClient()
  const refresh = () => {
    qc.invalidateQueries({ queryKey: calendarKeys.all })
    qc.invalidateQueries({ queryKey: ['card'] })
    qc.invalidateQueries({ queryKey: ['board'] })
  }
  const json = (body: unknown) => ({ body: JSON.stringify(body) })

  return {
    create: useMutation({
      mutationFn: (data: EventCreate) =>
        api<CalendarEvent>('/events', { method: 'POST', ...json(data) }),
      onSuccess: refresh,
    }),
    update: useMutation({
      mutationFn: ({ id, ...data }: EventUpdate & { id: number }) =>
        api<CalendarEvent>(`/events/${id}`, { method: 'PATCH', ...json(data) }),
      onSettled: refresh,
    }),
    remove: useMutation({
      mutationFn: (id: number) => api<void>(`/events/${id}`, { method: 'DELETE' }),
      onSuccess: refresh,
    }),
    setDueDate: useMutation({
      mutationFn: ({ cardId, due }: { cardId: number; due: string | null }) =>
        api(`/cards/${cardId}`, { method: 'PATCH', ...json({ due_date: due }) }),
      onSettled: refresh,
    }),
  }
}
