import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { api } from '../lib/api'
import { applyTheme, asPaper, asTheme, type Paper, type Theme } from '../lib/theme'
import type { UserSettings, UserSettingsUpdate } from '../lib/types'

/** Sunucudaki tema tercihini yerel uygulamayla esitler (baska cihazda secilen de gelir). */
export function useThemeSync() {
  const settings = useQuery({ queryKey: ['settings'], queryFn: () => api<UserSettings>('/settings/') })
  const data = settings.data
  useEffect(() => {
    if (data) applyTheme(asTheme(data.theme), asPaper(data.background))
  }, [data?.theme, data?.background]) // eslint-disable-line react-hooks/exhaustive-deps
}

/** Tema/zemin degisikligi: aninda uygular, sonra sunucuya kaydeder. */
export function useSaveTheme() {
  const qc = useQueryClient()
  const save = useMutation({
    mutationFn: (data: UserSettingsUpdate) => api<UserSettings>('/settings/', { method: 'PUT', body: JSON.stringify(data) }),
    onSuccess: (data) => qc.setQueryData(['settings'], data),
  })
  return {
    save,
    set: (theme: Theme, paper: Paper) => {
      applyTheme(theme, paper)
      save.mutate({ theme, background: paper })
    },
  }
}
