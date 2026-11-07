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
}
