import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError, ensureFreshToken } from '../lib/api'

export type Level = 'A1' | 'A2' | 'B1' | 'B2' | 'C1' | 'C2'
export type FocusArea = 'speaking' | 'writing' | 'vocab' | 'grammar'

export const LEVELS: Level[] = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2']
export const FOCUS_LABELS: Record<FocusArea, string> = {
  speaking: 'Konuşma',
  writing: 'Yazma',
  vocab: 'Kelime',
  grammar: 'Dil bilgisi',
}
export const CATEGORY_LABELS: Record<string, string> = {
  grammar: 'Dil bilgisi',
  tense: 'Zaman',
  preposition: 'Edat',
  article: 'Tanımlık',
  word_choice: 'Kelime seçimi',
  spelling: 'Yazım',
  other: 'Diğer',
}
export const SOURCE_LABELS: Record<string, string> = { local: 'Yerel', claude: 'Claude', self: 'Ben' }

export interface EnglishProfile {
  id: number
  target_level: Level
  current_level: Level | null
  daily_minutes: number
  focus: FocusArea[]
}
export interface ProfileInput {
  target_level: Level
  current_level: Level | null
  daily_minutes: number
  focus: FocusArea[]
}
export interface Vocab {
  id: number
  term: string
  meaning_tr: string
  example: string | null
  due_on: string
}
export interface Mistake {
  id: number
  source: string
  original: string
  corrected: string
  category: string
  explanation_tr: string | null
  created_at: string
}
export interface EnglishToday {
  profile: EnglishProfile | null
  due_vocab: Vocab[]
  top_categories: { category: string; count: number }[]
  practiced_today: boolean
  task: string | null
}
export interface EnglishProgress {
  streak_days: number
  weekly_minutes: { week: string; minutes: number }[]
  vocab_stats: { total: number; due: number; mature: number }
  mistakes_by_category: { week: string; category: string; count: number }[]
}
export interface CorrectionMistake {
  original: string
  corrected: string
  category: string
  explanation_tr?: string
}
export interface CorrectionResult {
  original: string
  corrected: string
  ok: boolean | null
  mistakes: CorrectionMistake[]
}
export interface CorrectResponse {
  results: CorrectionResult[]
  saved?: number
  pending_action_id?: number
  save_error?: string
}
export interface DialogResponse {
  reply: string
  corrections: unknown[]
}
export interface DialogTurn {
  role: 'user' | 'coach'
  text: string
}

export const englishKeys = {
  all: ['english'] as const,
  profile: ['english', 'profile'] as const,
  today: ['english', 'today'] as const,
  mistakes: (category: string) => ['english', 'mistakes', category] as const,
  progress: ['english', 'progress'] as const,
}

const json = (body: unknown) => ({ body: JSON.stringify(body) })

/** Profil yoksa (404) null doner; sayfa kurulum formunu gosterir. */
export function useEnglishProfile() {
  return useQuery({
    queryKey: englishKeys.profile,
    queryFn: async () => {
      try {
        return await api<EnglishProfile>('/english/profile')
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null
        throw e
      }
    },
    retry: false,
  })
}

export function useSaveProfile() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: ProfileInput) => api<EnglishProfile>('/english/profile', { method: 'PUT', ...json(body) }),
    onSettled: () => qc.invalidateQueries({ queryKey: englishKeys.all }),
  })
}

export function useEnglishToday() {
  return useQuery({ queryKey: englishKeys.today, queryFn: () => api<EnglishToday>('/english/today') })
}

export function useReviewVocab() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, grade }: { id: number; grade: number }) =>
      api(`/english/vocab/${id}/review`, { method: 'POST', ...json({ grade }) }),
    onSettled: () => qc.invalidateQueries({ queryKey: englishKeys.today }),
  })
}

export function useMistakes(category: string) {
  return useQuery({
    queryKey: englishKeys.mistakes(category),
    queryFn: () => api<Mistake[]>(`/english/mistakes?limit=200${category ? `&category=${category}` : ''}`),
  })
}

export function useDeleteMistake() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api(`/english/mistakes/${id}`, { method: 'DELETE' }),
    onSettled: () => qc.invalidateQueries({ queryKey: englishKeys.all }),
  })
}

export function useEnglishProgress() {
  return useQuery({ queryKey: englishKeys.progress, queryFn: () => api<EnglishProgress>('/english/progress?weeks=8') })
}

/** Asistan uclari yavas olabilir: 120 sn sonra istek kesilir. */
export const ASSISTANT_TIMEOUT_MS = 120_000

export function assistantErrorText(err: unknown): string {
  if (err instanceof DOMException && err.name === 'AbortError') return 'Yanıt gelmedi'
  if (err instanceof ApiError) {
    if (err.status === 503) return 'Yerel model yok ya da kapalı'
    // 500/504: asistan servisi kapalıyken proxy'nin ham hatası; 502'de sunucu mesajı anlamlı
    if (err.status === 500 || err.status === 504) return 'Asistana ulaşılamadı'
    return err.message
  }
  return 'Asistana ulaşılamadı'
}

async function assistantPost<T>(path: string, body: unknown): Promise<T> {
  await ensureFreshToken()
  const ctl = new AbortController()
  const timer = window.setTimeout(() => ctl.abort(), ASSISTANT_TIMEOUT_MS)
  try {
    return await api<T>(path, { method: 'POST', signal: ctl.signal, ...json(body) })
  } finally {
    window.clearTimeout(timer)
  }
}

export function useCorrect() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (sentences: string[]) => assistantPost<CorrectResponse>('/assistant/english/correct', { sentences }),
    onSettled: () => qc.invalidateQueries({ queryKey: englishKeys.all }),
  })
}

export function useDialog() {
  return useMutation({
    mutationFn: (v: { history: DialogTurn[]; user_text: string }) =>
      assistantPost<DialogResponse>('/assistant/english/dialog', v),
  })
}
