import { useSyncExternalStore } from 'react'

/** Tema ve uygulama zemini: <html data-theme data-paper>. Tercih localStorage'da (parlamasiz ilk boyama icin index.html'deki betik okur). */
export type Theme = 'system' | 'light' | 'dark'
export type Paper = 'kagit' | 'krem' | 'adacayi' | 'lavanta' | 'gri'

export const THEMES: Theme[] = ['system', 'light', 'dark']
export const PAPERS: { key: Paper; label: string; light: string; dark: string }[] = [
  { key: 'kagit', label: 'Kâğıt', light: '#f2f4f8', dark: '#0f1422' },
  { key: 'krem', label: 'Krem', light: '#f6f2e9', dark: '#18150f' },
  { key: 'adacayi', label: 'Adaçayı', light: '#edf3ee', dark: '#101a15' },
  { key: 'lavanta', label: 'Lavanta', light: '#f1eff8', dark: '#16142a' },
  { key: 'gri', label: 'Gri', light: '#f1f1f2', dark: '#141416' },
]

const KT = 'ajanda.theme'
const KP = 'ajanda.paper'

const isTheme = (v: unknown): v is Theme => THEMES.includes(v as Theme)
const isPaper = (v: unknown): v is Paper => PAPERS.some((p) => p.key === v)

function read(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}
function write(key: string, v: string) {
  try {
    localStorage.setItem(key, v)
  } catch {
    /* gizli pencere vb.: yok say */
  }
}

const mq = typeof window !== 'undefined' ? window.matchMedia('(prefers-color-scheme: dark)') : null
const resolve = (t: Theme): 'light' | 'dark' => (t === 'system' ? (mq?.matches ? 'dark' : 'light') : t)

const t0 = read(KT)
const p0 = read(KP)
let state = {
  theme: (isTheme(t0) ? t0 : 'system') as Theme,
  paper: (isPaper(p0) ? p0 : 'kagit') as Paper,
  resolved: 'light' as 'light' | 'dark',
}
const listeners = new Set<() => void>()

function commit(theme: Theme, paper: Paper) {
  const resolved = resolve(theme)
  const el = document.documentElement
  el.setAttribute('data-theme', resolved)
  el.setAttribute('data-paper', paper)
  if (state.theme === theme && state.paper === paper && state.resolved === resolved) return
  state = { theme, paper, resolved }
  listeners.forEach((l) => l())
}

/** Temayi uygular ve localStorage'a yazar (sunucuya yazmak cagirana ait). */
export function applyTheme(theme: Theme, paper: Paper) {
  write(KT, theme)
  write(KP, paper)
  commit(theme, paper)
}

// "Sistem" seciliyken isletim sistemi temasi degisince izle
mq?.addEventListener('change', () => {
  if (state.theme === 'system') commit('system', state.paper)
})
if (typeof document !== 'undefined') commit(state.theme, state.paper)

export function useTheme() {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb)
      return () => listeners.delete(cb)
    },
    () => state,
  )
}

/** Hizli dugme: gorunen temanin tersine acik secim yapar (acik <-> koyu). */
export const oppositeTheme = (resolved: 'light' | 'dark'): Theme => (resolved === 'dark' ? 'light' : 'dark')
export const asTheme = (v: string): Theme => (isTheme(v) ? v : 'system')
export const asPaper = (v: string): Paper => (isPaper(v) ? v : 'kagit')
