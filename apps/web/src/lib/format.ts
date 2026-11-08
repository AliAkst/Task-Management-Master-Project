import type { TaskPriority } from './types'

const dateFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short' })
const dateTimeFmt = new Intl.DateTimeFormat('tr-TR', {
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
})

export const formatShortDate = (iso: string) => dateFmt.format(new Date(iso))
export const formatDateTime = (iso: string) => dateTimeFmt.format(new Date(iso))

export const isOverdue = (iso: string | null | undefined) =>
  !!iso && new Date(iso).getTime() < Date.now()

export const PRIORITY_LABEL: Record<TaskPriority, string> = {
  low: 'Düşük',
  medium: 'Orta',
  high: 'Yüksek',
}

export const PRIORITY_DOT: Record<TaskPriority, string> = {
  low: 'bg-slate-300',
  medium: 'bg-amber-400',
  high: 'bg-red-500',
}

/** ISO tarih <-> <input type="date"> degeri (yerel gun). */
export function toDateInput(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** <input type="date"> degerini o gunun yerel 23:59'una cevirir (son tarih mantigi). */
export function fromDateInput(value: string): string | null {
  if (!value) return null
  const [y, m, d] = value.split('-').map(Number)
  return new Date(y, m - 1, d, 23, 59).toISOString()
}

export const ACTION_LABEL: Record<string, string> = {
  created: 'oluşturuldu',
  scheduled: 'takvime eklendi',
  unscheduled: 'takvimden çıkarıldı',
  updated: 'güncellendi',
  moved: 'taşındı',
  completed: 'tamamlandı',
  reopened: 'yeniden açıldı',
  archived: 'arşivlendi',
  unarchived: 'arşivden çıkarıldı',
  rescheduled: 'tarihi değişti',
  estimate_changed: 'süre tahmini değişti',
  deleted: 'silindi',
  checked: 'checklist maddesi işaretlendi',
  unchecked: 'checklist maddesi geri alındı',
  split: 'parçalara bölündü',
  dependency_added: 'ön koşul eklendi',
  dependency_removed: 'ön koşul kaldırıldı',
  unblocked: 'ön koşulları bitti, başlanabilir',
}

const pad = (n: number) => String(n).padStart(2, '0')

/** ISO -> <input type="datetime-local"> degeri (yerel saat). */
export function toLocalInput(iso: string | Date): string {
  const d = new Date(iso)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** <input type="datetime-local"> degeri -> ISO (UTC). */
export const fromLocalInput = (value: string) => new Date(value).toISOString()

const timeFmt = new Intl.DateTimeFormat('tr-TR', { hour: '2-digit', minute: '2-digit' })
const dayFmt = new Intl.DateTimeFormat('tr-TR', { weekday: 'short', day: 'numeric', month: 'short' })

/** "Sal 11 Kas 19:00–21:00" */
export function formatRange(startIso: string, endIso: string, allDay: boolean): string {
  const s = new Date(startIso)
  if (allDay) return `${dayFmt.format(s)} (tüm gün)`
  return `${dayFmt.format(s)} ${timeFmt.format(s)}–${timeFmt.format(new Date(endIso))}`
}

/** 3725 sn -> "1 sa 2 dk" (kisa, kart yuzu icin). */
export function formatDuration(sec: number): string {
  if (sec > 0 && sec < 60) return '<1 dk'
  const m = Math.round(sec / 60)
  if (m < 60) return `${m} dk`
  const h = Math.floor(m / 60)
  return m % 60 ? `${h} sa ${m % 60} dk` : `${h} sa`
}

/** 3725 sn -> "01:02:05" (canli kronometre icin). */
export function formatClock(sec: number): string {
  const s = Math.max(0, Math.floor(sec))
  return [Math.floor(s / 3600), Math.floor((s % 3600) / 60), s % 60]
    .map((n) => String(n).padStart(2, '0'))
    .join(':')
}

/** Dosya boyutu: 1,5 MB / 320 KB / 80 B */
export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`
  return `${(n / (1024 * 1024)).toFixed(1).replace('.', ',')} MB`
}
