import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'

/** Sunucu bildirimleri (Faz 13f): asistan servisindeki zamanlayici Telegram / Windows bildirimi yollar. */
export type NotifyKind = 'night_plan' | 'morning' | 'overdue' | 'weekly'

export interface NotifyChannel {
  kind: 'telegram' | 'toast'
  is_enabled: boolean
  last_error: string | null
  last_sent_at: string | null
  /** Yalniz Telegram: bot kullanici adi (token asla gelmez) */
  bot_username?: string | null
  paired?: boolean
}

export interface NotifyState {
  enabled: boolean
  channels: NotifyChannel[]
  settings: { kinds: Record<NotifyKind, boolean>; browser_reminders_off: boolean }
}

export const notifyKey = ['assistant', 'notify'] as const
const BASE = '/assistant/notify'
export const NOTIFY_TIMEOUT_MS = 15_000

/** 15 sn zaman asimi; ag hatasi/zaman asimi "Ulasilamadi" olur (G3). */
export async function notifyCall<T>(path: string, init: RequestInit = {}): Promise<T> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), NOTIFY_TIMEOUT_MS)
  try {
    return await api<T>(`${BASE}${path}`, { ...init, signal: ctrl.signal })
  } catch (e) {
    if (e instanceof Error && (e.name === 'AbortError' || e instanceof TypeError)) throw new Error('Ulaşılamadı')
    throw e
  } finally {
    clearTimeout(timer)
  }
}

export function useNotify() {
  return useQuery({
    queryKey: notifyKey,
    queryFn: () => notifyCall<NotifyState>(''),
    retry: false,
    staleTime: 30_000,
  })
}

/** Sunucu bildirimi acik ve en az bir kanal etkin + "tarayici bildirimlerini kapat" secili mi? */
export function useBrowserRemindersOff(): boolean {
  const { data } = useNotify()
  if (!data?.enabled) return false
  return data.settings.browser_reminders_off && data.channels.some((c) => c.is_enabled)
}

export function useNotifyActions() {
  const qc = useQueryClient()
  const settled = () => qc.invalidateQueries({ queryKey: notifyKey })
  const send = <T,>(path: string, method: string, body?: unknown) =>
    notifyCall<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) })
  return {
    enable: useMutation({ mutationFn: () => send('/enable', 'POST'), onSettled: settled }),
    disable: useMutation({ mutationFn: () => send('/disable', 'POST'), onSettled: settled }),
    saveTelegram: useMutation({
      mutationFn: (botToken: string) => send<{ bot_username: string | null }>('/telegram', 'PUT', { bot_token: botToken }),
      onSettled: settled,
    }),
    pair: useMutation({ mutationFn: () => send<NotifyChannel>('/telegram/pair', 'POST'), onSettled: settled }),
    removeTelegram: useMutation({ mutationFn: () => send('/telegram', 'DELETE'), onSettled: settled }),
    setToast: useMutation({ mutationFn: (enabled: boolean) => send('/toast', 'PUT', { enabled }), onSettled: settled }),
    saveSettings: useMutation({
      mutationFn: (body: { kinds?: Partial<Record<NotifyKind, boolean>>; browser_reminders_off?: boolean }) =>
        send('/settings', 'PUT', body),
      onSettled: settled,
    }),
    test: useMutation({
      mutationFn: () => send<{ results: Record<string, 'ok' | 'hata'> }>('/test', 'POST'),
      onSettled: settled,
    }),
  }
}
