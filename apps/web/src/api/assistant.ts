import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
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

/** AI'in yazma islemi (oneri ya da yapilmis). */
export interface AiAction {
  id: number
  action_type: string
  summary: string
  status: 'proposed' | 'executed' | 'rejected' | 'failed'
  result: Record<string, unknown> | null
  user_feedback: string | null
}

export interface Permission {
  action_type: string
  label: string
  mode: 'ask' | 'auto' | 'never'
}

export interface ChatMessage {
  id: number | string
  role: 'user' | 'assistant'
  content: string | null
  tools: string[]
  actions?: AiAction[]
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
  | {
      event: 'start'
      data: {
        conversation_id: number
        model_id: string
        model_label: string
        model_source: 'message' | 'board' | 'user'
        is_local: boolean
        dropped_local_messages: number
      }
    }
  | { event: 'token'; data: { text: string } }
  | { event: 'tool_start'; data: { id: string; name: string; arguments: Record<string, unknown> } }
  | { event: 'tool_end'; data: { id: string; name: string; ok: boolean } }
  | { event: 'action'; data: AiAction }
  | { event: 'done'; data: { conversation_id: number } }
  | { event: 'error'; data: { message: string } }

/**
 * Sohbet mesajini gonderir ve SSE olaylarini sirayla `onEvent`e verir.
 * (EventSource POST desteklemedigi icin fetch + stream okuyucu.)
 */
export async function streamChat(
  body: { message: string; conversation_id: number | null; model_id: string | null; board_id: number | null },
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
  create_card: 'kart önerdi',
  update_card: 'kart güncellemesi önerdi',
  add_note: 'not önerdi',
  create_event: 'takvim önerdi',
  split_card: 'bölme önerdi',
  link_cards: 'bağlantı önerdi',
  plan_day: 'plan önerdi',
  schedule_day: 'günü planlıyor',
}

// ---------------- islemler & izinler ----------------
/** Onay/ret sonrasi: AI'in degistirdigi uygulama verilerini ve sohbeti tazele. */
function useRefreshAfterAction() {
  const qc = useQueryClient()
  return () => {
    for (const key of [['board'], ['boards'], ['card'], ['calendar'], ['day'], ['analytics'], ['assistant']]) {
      qc.invalidateQueries({ queryKey: key })
    }
  }
}

export function useActionDecision() {
  const refresh = useRefreshAfterAction()
  return {
    approve: useMutation({
      mutationFn: ({ id, rememberAuto, excludeCardIds }: { id: number; rememberAuto: boolean; excludeCardIds?: number[] }) =>
        api<AiAction>(`${BASE}/actions/${id}/approve`, {
          method: 'POST',
          body: JSON.stringify({ remember_auto: rememberAuto, exclude_card_ids: excludeCardIds ?? [] }),
        }),
      onSuccess: refresh,
    }),
    reject: useMutation({
      mutationFn: ({ id, reason }: { id: number; reason: string | null }) =>
        api<AiAction>(`${BASE}/actions/${id}/reject`, {
          method: 'POST',
          body: JSON.stringify({ reason }),
        }),
      onSuccess: refresh,
    }),
  }
}

export function usePermissions() {
  return useQuery({
    queryKey: ['assistant', 'permissions'],
    queryFn: () => api<Permission[]>(`${BASE}/permissions`),
  })
}

export function useSetPermission() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ actionType, mode }: { actionType: string; mode: Permission['mode'] }) =>
      api(`${BASE}/permissions/${actionType}`, { method: 'PUT', body: JSON.stringify({ mode }) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['assistant', 'permissions'] }),
  })
}

// ---------------- model saglayicilari ----------------
export type CloudProviderId = 'anthropic' | 'openai' | 'gemini'

export interface ProviderConfig {
  provider: CloudProviderId
  label: string
  key_url: string
  suggested_models: string[]
  connected: boolean
  key_hint: string | null // "…ab12"; anahtarin kendisi asla gelmez
  models: string[]
  is_enabled: boolean
  base_url: string | null
  updated_at: string | null
}

export interface ProviderSave {
  api_key?: string | null
  models: string[]
  is_enabled: boolean
  base_url?: string | null
}

const providersKey = ['assistant', 'providers'] as const
const prefsKey = ['assistant', 'preferences'] as const

export function useProviders() {
  return useQuery({ queryKey: providersKey, queryFn: () => api<ProviderConfig[]>(`${BASE}/providers`) })
}

export function useProviderMutations() {
  const qc = useQueryClient()
  const refresh = () => {
    qc.invalidateQueries({ queryKey: providersKey })
    qc.invalidateQueries({ queryKey: assistantKeys.models })
  }
  return {
    save: useMutation({
      mutationFn: ({ provider, data }: { provider: CloudProviderId; data: ProviderSave }) =>
        api<ProviderConfig>(`${BASE}/providers/${provider}`, { method: 'PUT', body: JSON.stringify(data) }),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (provider: CloudProviderId) => api<void>(`${BASE}/providers/${provider}`, { method: 'DELETE' }),
      onSuccess: refresh,
    }),
    /** Anahtari dogrular: saglayicinin ucretsiz model listesi cagrisi (token harcamaz). */
    test: useMutation({
      mutationFn: ({ provider, api_key, base_url }: { provider: CloudProviderId; api_key?: string; base_url?: string | null }) =>
        api<{ models: string[] }>(`${BASE}/providers/${provider}/test`, {
          method: 'POST',
          body: JSON.stringify({ api_key: api_key || null, base_url: base_url || null }),
        }),
    }),
  }
}

export interface ModelPrefs {
  default_model_id: string
  /** null: onerilen buyuk local model (suggested_background_model) */
  background_model_id: string | null
  suggested_background_model: string
}

export function useModelPrefs() {
  return useQuery({ queryKey: prefsKey, queryFn: () => api<ModelPrefs>(`${BASE}/preferences`) })
}

function useSavePrefs() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<Pick<ModelPrefs, 'default_model_id' | 'background_model_id'>>) =>
      api<ModelPrefs>(`${BASE}/preferences`, { method: 'PUT', body: JSON.stringify(data) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: prefsKey })
      qc.invalidateQueries({ queryKey: assistantKeys.models })
    },
  })
}

export function useSetDefaultModel() {
  const m = useSavePrefs()
  return { ...m, mutate: (default_model_id: string) => m.mutate({ default_model_id }) }
}

export function useSetBackgroundModel() {
  const m = useSavePrefs()
  return { ...m, mutate: (background_model_id: string | null) => m.mutate({ background_model_id }) }
}

// ---------------- gun sonu isi (ozet + yarin plan onerisi) ----------------
export interface DayReviewPlanItem {
  title: string
  kind: string
  card_id: number | null
  event_id: number | null
  minutes: number | null
  adjusted_minutes: number | null
  planned_start: string | null
  reason: string | null
}

export interface DayReviewJob {
  id: number
  date: string
  status: 'queued' | 'running' | 'done' | 'failed'
  model_id: string
  model_label: string
  is_local: boolean
  error: string | null
  action: AiAction | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  result: {
    summary: string | null
    tip: string | null
    tomorrow: string
    plan: DayReviewPlanItem[]
    estimate_factor: number | null
    estimate_text: string | null
    cap_minutes: number
    candidate_count: number
    action_status: AiAction['status'] | null
    notes: string[]
  } | null
}

const jobKey = (day: string) => ['assistant', 'day-review', day] as const
const isActive = (j: { status: string } | null | undefined) => j?.status === 'queued' || j?.status === 'running'

/** Is surerken 5 sn'de bir yoklanir; bitince gunun plani/ozeti tazelenir. */
export function useDayReviewJob(day: string, enabled = true) {
  return useQuery({
    queryKey: jobKey(day),
    queryFn: () => api<DayReviewJob | null>(`${BASE}/day-review/${day}`),
    enabled,
    refetchInterval: (q) => (isActive(q.state.data) ? 5000 : false),
  })
}

export function useStartDayReview() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (day: string) => api<DayReviewJob>(`${BASE}/day-review/${day}`, { method: 'POST' }),
    onSuccess: (job) => qc.setQueryData(jobKey(job.date), job),
  })
}

// ---------------- Gelen Kutusu dagitimi (Faz 7d) ----------------
export interface InboxTriageMove {
  card_id: number
  title: string
  board_id: number
  board: string
  list_id: number
  list: string
  reason: string | null
}

export interface InboxTriageJob {
  id: number
  status: 'queued' | 'running' | 'done' | 'failed'
  model_label: string
  is_local: boolean
  error: string | null
  action: AiAction | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  result: {
    moves: InboxTriageMove[]
    candidate_count: number
    action_status: AiAction['status'] | null
    notes: string[]
  } | null
}

const triageKey = ['assistant', 'inbox-triage'] as const

/** Is surerken 5 sn'de bir yoklanir. */
export function useInboxTriageJob(enabled = true) {
  return useQuery({
    queryKey: triageKey,
    queryFn: () => api<InboxTriageJob | null>(`${BASE}/inbox-triage`),
    enabled,
    refetchInterval: (q) => (isActive(q.state.data) ? 5000 : false),
  })
}

export function useStartInboxTriage() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api<InboxTriageJob>(`${BASE}/inbox-triage`, { method: 'POST' }),
    onSuccess: (job) => qc.setQueryData(triageKey, job),
  })
}

/** Bulut modele gecerken gosterilen ucret uyarisi (tek kaynak). */
export const CLOUD_COST_WARNING =
  'Bu bir bulut modeli: mesajların sağlayıcının sunucusuna gider ve her mesaj sağlayıcı hesabından ücretlendirilebilir.'
