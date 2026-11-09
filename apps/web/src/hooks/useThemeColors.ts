import { useMemo } from 'react'
import { useTheme } from '../lib/theme'

const VARS = {
  paper: '--color-slate-50',
  surface: '--color-surface',
  grid: '--color-slate-200',
  cursor: '--color-slate-100',
  axis: '--color-slate-500',
  legend: '--color-slate-600',
  edge: '--color-slate-400',
  ok: '--chart-ok',
  warn: '--chart-warn',
  s1: '--chart-1',
  s2: '--chart-2',
  s3: '--chart-3',
  s4: '--chart-4',
} as const

export type ThemeColors = Record<keyof typeof VARS, string>

/** Tema degisince CSS degiskenlerini okuyup grafik/inline renkler icin dondurur. */
export function useThemeColors(): ThemeColors {
  const { resolved, paper } = useTheme()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => {
    const cs = getComputedStyle(document.documentElement)
    return Object.fromEntries(
      Object.entries(VARS).map(([k, v]) => [k, cs.getPropertyValue(v).trim()]),
    ) as ThemeColors
  }, [resolved, paper])
}
