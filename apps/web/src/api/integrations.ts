import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'

/** Bagli hesap; gizli degerler sunucudan sadece maskeli (son 4 karakter) gelir. */
export interface IntegrationAccount {
  provider: string
  account_label: string | null
  status: 'active' | 'error'
  scopes: string | null
  last_synced_at: string | null
  last_error: string | null
  masked_credentials: Record<string, string>
  settings: Record<string, unknown> | null
  /** Yalniz Microsoft: Calendars.Read izni verilmis mi (Teams toplantilari). */
  calendar_consent?: boolean | null
}

/** Microsoft takvim (Teams toplantilari) ayarlari: account.settings.calendar. */
export interface MicrosoftCalendarSettings {
  enabled: boolean
  teams_only: boolean
  board_id: number | null
  weeks_ahead: number
  last_synced_at?: string | null
  last_error?: string | null
}

export const CALENDAR_DEFAULTS: MicrosoftCalendarSettings = {
  enabled: false,
  teams_only: true,
  board_id: null,
  weeks_ahead: 2,
}

export function calendarSettings(account: IntegrationAccount | undefined): MicrosoftCalendarSettings {
  return { ...CALENDAR_DEFAULTS, ...((account?.settings?.calendar as Partial<MicrosoftCalendarSettings> | undefined) ?? {}) }
}

export interface GoogleCalendarInfo {
  id: string
  summary: string
  primary: boolean
  color: string | null
  selected: boolean
}

export interface SyncSummary {
  created: number
  updated: number
  removed: number
  errors: string[]
}

export interface TrelloBoardInfo {
  id: string
  name: string
  url: string | null
  already_imported: boolean
}

export interface TrelloImportResult {
  trello_board_id: string
  name: string
  board_id: number | null
  created_board: boolean
  lists: number
  cards: number
  checklist_items: number
  notes: number
  skipped_cards: number
  error: string | null
}

export interface TodoListInfo {
  id: string
  name: string
  selected: boolean
}

export interface MicrosoftStatus {
  pending_push: number
  failed_push: number
}

/** Google/Microsoft uygulama kimligi girilmis mi (sir hicbir zaman donmez). */
export interface OAuthClientInfo {
  provider: 'google' | 'microsoft'
  configured: boolean
  source: 'app' | 'env' | null
  client_id: string | null
  redirect_uri: string
}

const keys = {
  all: ['integrations'] as const,
  oauthClients: ['integrations', 'oauth-clients'] as const,
  microsoftLists: ['integrations', 'microsoft', 'lists'] as const,
  microsoftStatus: ['integrations', 'microsoft', 'status'] as const,
  trelloBoards: ['integrations', 'trello', 'boards'] as const,
  googleCalendars: ['integrations', 'google', 'calendars'] as const,
}

export function useIntegrations() {
  return useQuery({
    queryKey: keys.all,
    queryFn: () => api<IntegrationAccount[]>('/integrations'),
  })
}

/** Takvimi acik, izinli Microsoft hesabi var mi (takvim sayfasindaki "Toplantilari cek" icin). */
export function useMicrosoftCalendarEnabled() {
  const accounts = useIntegrations()
  const ms = accounts.data?.find((a) => a.provider === 'microsoft')
  return !!ms && ms.status === 'active' && !!ms.calendar_consent && calendarSettings(ms).enabled
}

export function useOAuthClients() {
  return useQuery({
    queryKey: keys.oauthClients,
    queryFn: () => api<OAuthClientInfo[]>('/integrations/oauth-clients'),
  })
}

export function useTrelloBoards(enabled: boolean) {
  return useQuery({
    queryKey: keys.trelloBoards,
    queryFn: () => api<TrelloBoardInfo[]>('/integrations/trello/boards'),
    enabled,
    retry: false,
  })
}

export function useGoogleCalendars(enabled: boolean) {
  return useQuery({
    queryKey: keys.googleCalendars,
    queryFn: () => api<GoogleCalendarInfo[]>('/integrations/google/calendars'),
    enabled,
    retry: false,
  })
}

export function useMicrosoftLists(enabled: boolean) {
  return useQuery({
    queryKey: keys.microsoftLists,
    queryFn: () => api<TodoListInfo[]>('/integrations/microsoft/lists'),
    enabled,
    retry: false,
  })
}

/** Geri yazilmayi bekleyen / hata almis tamamlamalar (bekleyen varken 10 sn'de bir yoklar). */
export function useMicrosoftStatus(enabled: boolean) {
  return useQuery({
    queryKey: keys.microsoftStatus,
    queryFn: () => api<MicrosoftStatus>('/integrations/microsoft/status'),
    enabled,
    retry: false,
    refetchInterval: (q) => (q.state.data?.pending_push ? 10_000 : false),
  })
}

export function useIntegrationMutations() {
  const qc = useQueryClient()
  // Hesap ya da icerik degisince: hesap listesi, Trello board'lari ve app board'lari
  const refresh = () => {
    qc.invalidateQueries({ queryKey: keys.all })
    qc.invalidateQueries({ queryKey: ['boards'] })
  }
  return {
    connectTrello: useMutation({
      mutationFn: (data: { api_key: string; token: string }) =>
        api<IntegrationAccount>('/integrations/trello', { method: 'PUT', body: JSON.stringify(data) }),
      onSuccess: refresh,
    }),
    disconnect: useMutation({
      mutationFn: (provider: string) => api<void>(`/integrations/${provider}`, { method: 'DELETE' }),
      onSuccess: () => {
        qc.removeQueries({ queryKey: keys.trelloBoards })
        qc.removeQueries({ queryKey: keys.googleCalendars })
        qc.removeQueries({ queryKey: keys.microsoftLists })
        qc.removeQueries({ queryKey: keys.microsoftStatus })
        qc.invalidateQueries({ queryKey: ['calendar'] })
        refresh()
      },
    }),
    // OAuth: izin ekraninin adresini al, sayfayi oraya yonlendir
    connectOAuth: useMutation({
      mutationFn: (provider: string) =>
        api<{ authorize_url: string }>(`/integrations/${provider}/connect`, { method: 'POST' }),
      onSuccess: (r) => window.location.assign(r.authorize_url),
    }),
    // Kurulum sihirbazi: client id/secret kaydet (sonra connectOAuth)
    saveOAuthClient: useMutation({
      mutationFn: ({ provider, ...data }: { provider: string; client_id: string; client_secret: string }) =>
        api<OAuthClientInfo>(`/integrations/${provider}/oauth-client`, { method: 'PUT', body: JSON.stringify(data) }),
      onSuccess: () => qc.invalidateQueries({ queryKey: keys.oauthClients }),
    }),
    deleteOAuthClient: useMutation({
      mutationFn: (provider: string) => api<void>(`/integrations/${provider}/oauth-client`, { method: 'DELETE' }),
      onSuccess: () => qc.invalidateQueries({ queryKey: keys.oauthClients }),
    }),
    saveGoogleSettings: useMutation({
      mutationFn: (data: { calendar_ids: string[]; board_id: number | null }) =>
        api<IntegrationAccount>('/integrations/google/settings', { method: 'PUT', body: JSON.stringify(data) }),
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: keys.all })
        qc.invalidateQueries({ queryKey: keys.googleCalendars })
        qc.invalidateQueries({ queryKey: ['calendar'] })
      },
    }),
    saveMicrosoftSettings: useMutation({
      mutationFn: (listIds: string[] | null) =>
        api<IntegrationAccount>('/integrations/microsoft/settings', {
          method: 'PUT',
          body: JSON.stringify({ list_ids: listIds }),
        }),
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: keys.all })
        qc.invalidateQueries({ queryKey: keys.microsoftLists })
      },
    }),
    saveMicrosoftCalendar: useMutation({
      mutationFn: (data: { enabled: boolean; teams_only: boolean; board_id: number | null; weeks_ahead: number }) =>
        api<IntegrationAccount>('/integrations/microsoft/calendar', { method: 'PUT', body: JSON.stringify(data) }),
      onSettled: () => {
        qc.invalidateQueries({ queryKey: keys.all })
        qc.invalidateQueries({ queryKey: ['calendar'] })
      },
    }),
    syncMicrosoftCalendar: useMutation({
      mutationFn: () => api<SyncSummary>('/integrations/microsoft/calendar/sync', { method: 'POST' }),
      onSettled: () => {
        qc.invalidateQueries({ queryKey: keys.all })
        qc.invalidateQueries({ queryKey: ['calendar'] })
      },
    }),
    syncNow: useMutation({
      mutationFn: (provider: string) =>
        api<SyncSummary>(`/integrations/${provider}/sync`, { method: 'POST' }),
      onSettled: () => {
        qc.invalidateQueries({ queryKey: keys.all })
        qc.invalidateQueries({ queryKey: keys.microsoftStatus })
        qc.invalidateQueries({ queryKey: ['calendar'] })
        qc.invalidateQueries({ queryKey: ['boards'] })
        qc.invalidateQueries({ queryKey: ['cards'] })
      },
    }),
    importTrello: useMutation({
      mutationFn: (boardIds: string[]) =>
        api<TrelloImportResult[]>('/integrations/trello/import', {
          method: 'POST',
          body: JSON.stringify({ board_ids: boardIds }),
        }),
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: keys.trelloBoards })
        refresh()
      },
    }),
  }
}
