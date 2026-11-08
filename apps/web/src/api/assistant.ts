import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { useAuthStore } from '../stores/auth'

export interface ModelOption {
  id: string
  label: string
  provider: string
  is_local: boolean
}

export interface Conversation {
  id: number
  title: string
  updated_at: string
}

export interface ChatMessage {
  id: number | string
  role: 'user' | 'assistant'
  content: string | null
  tools: string[]
  model_id?: string | null
  is_local?: boolean
}

export const assistantKeys = {
  models: ['assistant', 'models'] as const,
  conversations: ['assistant', 'conversations'] as const,
  messages: (id: number) => ['assistant', 'messages', id] as const,
}

const BASE = '/assistant'

export function useModels() {
  return useQuery({
    queryKey: assistantKeys.models,
    queryFn: () => api<{ default: string; models: ModelOption[] }>(`${BASE}/models`),
    staleTime: 60_000,
  })
}

export function useConversations() {
  return useQuery({
    queryKey: assistantKeys.conversations,
    queryFn: () => api<Conversation[]>(`${BASE}/conversations`),
  })
}

export function useMessages(id: number | null) {
  return useQuery({
    queryKey: assistantKeys.messages(id ?? 0),
    queryFn: () => api<ChatMessage[]>(`${BASE}/conversations/${id}/messages`),
    enabled: id !== null,
  })
}

export const deleteConversation = (id: number) =>
  api<void>(`${BASE}/conversations/${id}`, { method: 'DELETE' })

// ---------------- SSE ----------------
export type StreamEvent =
  | { event: 'start'; data: { conversation_id: number; model_id: string; is_local: boolean; dropped_local_messages: number } }
  | { event: 'token'; data: { text: string } }
  | { event: 'tool_start'; data: { id: string; name: string; arguments: Record<string, unknown> } }
  | { event: 'tool_end'; data: { id: string; name: string; ok: boolean } }
  | { event: 'done'; data: { conversation_id: number } }
  | { event: 'error'; data: { message: string } }

/**
 * Sohbet mesajini gonderir ve SSE olaylarini sirayla `onEvent`e verir.
 * (EventSource POST desteklemedigi icin fetch + stream okuyucu.)
 */
export async function streamChat(
  body: { message: string; conversation_id: number | null; model_id: string | null },
  onEvent: (e: StreamEvent) => void,
  signal: AbortSignal,
  retried = false,
): Promise<void> {
  const token = useAuthStore.getState().accessToken
  const res = await fetch(`/api/v1${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
    signal,
  })
  if (res.status === 401 && !retried) {
    await api('/auth/me') // 401'de token'i yeniler
    return streamChat(body, onEvent, signal, true)
  }
  if (!res.ok || !res.body) {
    const err = await res.json().catch(() => null)
    throw new Error(err?.error?.message ?? `Asistan hatası (${res.status})`)
  }

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value
    let sep: number
    while ((sep = buffer.indexOf('\n\n')) !== -1) {
      const block = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)
      let event = 'message'
      let data = ''
      for (const line of block.split('\n')) {
        if (line.startsWith('event: ')) event = line.slice(7)
        else if (line.startsWith('data: ')) data += line.slice(6)
      }
      if (data) onEvent({ event, data: JSON.parse(data) } as StreamEvent)
    }
  }
}

/** Arac adlarinin kullaniciya gosterilen Turkce karsiliklari. */
export const TOOL_LABEL: Record<string, string> = {
  list_boards: "board'larına baktı",
  get_board: "board'u inceledi",
  search_cards: 'kartlarda aradı',
  get_card: 'kart detayına baktı',
  get_calendar: 'takvime baktı',
  get_day_plan: 'gün planına baktı',
  get_stats_summary: 'istatistiklerine baktı',
}
