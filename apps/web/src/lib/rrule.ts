/**
 * RRULE (RFC 5545) yardimcilari: arayuzun urettigi basit kurallar ve
 * okunur Turkce aciklama. Sunucu kurali dogrular ve tekrarlari hesaplar.
 */

export const WEEKDAYS = [
  { code: 'MO', short: 'Pzt', long: 'Pazartesi' },
  { code: 'TU', short: 'Sal', long: 'Salı' },
  { code: 'WE', short: 'Çar', long: 'Çarşamba' },
  { code: 'TH', short: 'Per', long: 'Perşembe' },
  { code: 'FR', short: 'Cum', long: 'Cuma' },
  { code: 'SA', short: 'Cmt', long: 'Cumartesi' },
  { code: 'SU', short: 'Paz', long: 'Pazar' },
] as const
export type DayCode = (typeof WEEKDAYS)[number]['code']
const WORKDAYS: DayCode[] = ['MO', 'TU', 'WE', 'TH', 'FR']

export type Mode = 'none' | 'daily' | 'weekdays' | 'weekly' | 'monthly' | 'yearly' | 'custom'

export interface RuleState {
  mode: Mode
  days: DayCode[] // weekly
  until: string // YYYY-MM-DD ya da ''
  raw: string // custom
}

function parts(rule: string): Record<string, string> {
  return Object.fromEntries(
    rule
      .replace(/^RRULE:/i, '')
      .split(';')
      .filter(Boolean)
      .map((p) => p.split('=') as [string, string])
      .map(([k, v]) => [k.toUpperCase(), (v ?? '').toUpperCase()]),
  )
}

const untilToDate = (u: string | undefined) =>
  u && /^\d{8}/.test(u) ? `${u.slice(0, 4)}-${u.slice(4, 6)}-${u.slice(6, 8)}` : ''

/** Kayitli kural -> secici durumu (taninmayan kural "custom" olur). */
export function parseRule(rule: string | null | undefined, fallbackDay: DayCode): RuleState {
  const empty: RuleState = { mode: 'none', days: [fallbackDay], until: '', raw: '' }
  if (!rule) return empty
  const p = parts(rule)
  const known = new Set(['FREQ', 'BYDAY', 'UNTIL'])
  const simple = Object.keys(p).every((k) => known.has(k))
  const until = untilToDate(p.UNTIL)
  const days = (p.BYDAY ?? '').split(',').filter(Boolean) as DayCode[]
  if (simple && p.FREQ === 'DAILY' && !p.BYDAY) return { ...empty, mode: 'daily', until }
  if (simple && p.FREQ === 'WEEKLY') {
    if (days.length === 5 && WORKDAYS.every((d) => days.includes(d))) return { ...empty, mode: 'weekdays', until }
    return { ...empty, mode: 'weekly', days: days.length ? days : [fallbackDay], until }
  }
  if (simple && p.FREQ === 'MONTHLY' && !p.BYDAY) return { ...empty, mode: 'monthly', until }
  if (simple && p.FREQ === 'YEARLY' && !p.BYDAY) return { ...empty, mode: 'yearly', until }
  return { ...empty, mode: 'custom', raw: rule }
}

/** Secici durumu -> kural (null: tekrarlanmaz). */
export function buildRule(s: RuleState): string | null {
  const until = s.until ? `;UNTIL=${s.until.split('-').join('')}T235959` : ''
  switch (s.mode) {
    case 'none':
      return null
    case 'daily':
      return `FREQ=DAILY${until}`
    case 'weekdays':
      return `FREQ=WEEKLY;BYDAY=${WORKDAYS.join(',')}${until}`
    case 'weekly': {
      const ordered = WEEKDAYS.map((d) => d.code).filter((c) => s.days.includes(c))
      return `FREQ=WEEKLY;BYDAY=${(ordered.length ? ordered : ['MO']).join(',')}${until}`
    }
    case 'monthly':
      return `FREQ=MONTHLY${until}`
    case 'yearly':
      return `FREQ=YEARLY${until}`
    case 'custom':
      return s.raw.trim() || null
  }
}

const untilFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'long', year: 'numeric' })

/** "Her hafta Pzt, Çar ve Cum" gibi okunur aciklama. */
export function describeRule(rule: string | null | undefined): string | null {
  if (!rule) return null
  const p = parts(rule)
  const n = Number(p.INTERVAL ?? 1)
  const days = (p.BYDAY ?? '').split(',').filter(Boolean)
  const dayNames = days.map((c) => WEEKDAYS.find((d) => d.code === c.slice(-2))?.short ?? c)
  const list = dayNames.length > 1 ? `${dayNames.slice(0, -1).join(', ')} ve ${dayNames[dayNames.length - 1]}` : dayNames[0]
  let text: string
  switch (p.FREQ) {
    case 'DAILY':
      text = n > 1 ? `${n} günde bir` : 'Her gün'
      break
    case 'WEEKLY':
      if (days.length === 5 && WORKDAYS.every((d) => days.includes(d)) && n === 1) text = 'Hafta içi her gün'
      else text = `${n > 1 ? `${n} haftada bir` : 'Her hafta'}${list ? ` ${list}` : ''}`
      break
    case 'MONTHLY':
      text = n > 1 ? `${n} ayda bir` : 'Her ay'
      break
    case 'YEARLY':
      text = n > 1 ? `${n} yılda bir` : 'Her yıl'
      break
    default:
      return rule
  }
  const until = untilToDate(p.UNTIL)
  if (until) text += `, ${untilFmt.format(new Date(`${until}T12:00`))} tarihine kadar`
  if (p.COUNT) text += `, ${p.COUNT} kez`
  return text
}

/** Tarihin haftanin gunu kodu (Pazartesi=MO). */
export function dayCodeOf(date: Date): DayCode {
  return WEEKDAYS[(date.getDay() + 6) % 7].code
}
