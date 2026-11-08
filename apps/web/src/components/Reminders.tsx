import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Video } from 'lucide-react'
import { localDay, shiftDay, useDayPlan } from '../api/dayPlans'
import { api } from '../lib/api'
import type { CalendarItem, UserSettings } from '../lib/types'
import { safeHttpsUrl } from './EventDialog'

/**
 * Planlama / gun sonu hatirlaticilari.
 * Uygulama acikken calisir: saat geldiyse ve is yapilmadiysa uygulama ici serit +
 * (izin verildiyse) gunde bir kez tarayici bildirimi. Tarayici kapaliyken bildirim
 * gelmez; bunun icin sunucu tarafli push gerekir (ileride, Docker kurulunca).
 */

const EVENING_PLANNING_HOUR = 15 // bu saatten sonraki planlama -> ertesi gunu planlar
const MEETING_LEAD_MS = 5 * 60_000 // toplanti baslamadan kac dk once "Katil" gosterilir

function minutesOf(t: string | null): number | null {
  if (!t) return null
  const [h, m] = t.split(':').map(Number)
  return h * 60 + m
}

function storageGet(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}
function storageSet(key: string, value: string) {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* gizli sekme vb. */
  }
}

function notifyOnce(key: string, title: string, body: string) {
  if (storageGet(`notified:${key}`)) return
  storageSet(`notified:${key}`, '1')
  try {
    if ('Notification' in window && Notification.permission === 'granted') {
      const n = new Notification(title, { body, tag: key })
      n.onclick = () => {
        window.focus()
        if (key.startsWith('meeting:')) return // sadece pencereyi one getir; "Katil" seritte
        window.location.assign(key.startsWith('review') ? '/today?mode=review' : `/today?mode=plan`)
      }
    }
  } catch {
    /* bildirim desteklenmiyor */
  }
}

export default function Reminders() {
  const settings = useQuery({ queryKey: ['settings'], queryFn: () => api<UserSettings>('/settings/') })
  const [now, setNow] = useState(() => new Date())
  const [, force] = useState(0)

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 30_000)
    return () => clearInterval(id)
  }, [])

  const today = localDay(now)
  const planTime = minutesOf(settings.data?.planning_time ?? null)
  const planTarget = planTime != null && planTime >= EVENING_PLANNING_HOUR * 60 ? shiftDay(today, 1) : today
  const todayPlan = useDayPlan(today)
  const targetPlan = useDayPlan(planTarget)
  // Bugunun cevrimici toplantilari (takvim; dakikada bir tazelenir)
  const dayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const dayEnd = new Date(dayStart.getTime() + 24 * 60 * 60_000)
  const meetings = useQuery({
    queryKey: ['calendar', 'reminders', today],
    queryFn: () => {
      const q = new URLSearchParams({ start: dayStart.toISOString(), end: dayEnd.toISOString() })
      return api<{ items: CalendarItem[] }>(`/calendar?${q}`).then((r) => r.items.filter((i) => i.kind === 'event' && i.meeting_url))
    },
    enabled: !!settings.data?.reminders_enabled,
    refetchInterval: 60_000,
    retry: false,
  })

  if (!settings.data?.reminders_enabled) return null
  const nowMin = now.getHours() * 60 + now.getMinutes()
  const reviewTime = minutesOf(settings.data.review_time)

  const banners: { key: string; text: string; link: string; cta: string; external?: boolean }[] = []

  for (const ev of meetings.data ?? []) {
    const url = safeHttpsUrl(ev.meeting_url)
    const startsIn = new Date(ev.start).getTime() - now.getTime()
    if (!url || startsIn > MEETING_LEAD_MS || (ev.end && new Date(ev.end).getTime() <= now.getTime())) continue
    const mins = Math.max(0, Math.ceil(startsIn / 60_000))
    banners.push({
      key: `meeting:${ev.id}`,
      text: startsIn <= 0 ? `«${ev.title}» toplantısı başladı.` : `«${ev.title}» toplantısı ${mins} dk sonra başlıyor.`,
      link: url,
      cta: 'Katıl',
      external: true,
    })
  }

  if (planTime != null && nowMin >= planTime && targetPlan.data && !targetPlan.data.exists) {
    const key = `plan:${planTarget}`
    const text = planTarget === today ? 'Bugünü henüz planlamadın.' : 'Yarını planlama zamanı.'
    banners.push({ key, text, link: planTarget === today ? '/today?mode=plan' : `/today?date=${planTarget}&mode=plan`, cta: 'Planla' })
  }
  if (reviewTime != null && nowMin >= reviewTime && todayPlan.data && todayPlan.data.status !== 'reviewed') {
    banners.push({ key: `review:${today}`, text: 'Günü değerlendirme zamanı.', link: '/today?mode=review', cta: 'Değerlendir' })
  }

  const visible = banners.filter((b) => !storageGet(`dismissed:${b.key}`))
  visible.forEach((b) => notifyOnce(b.key, 'Yaşam Planlayıcı', b.text))
  if (visible.length === 0) return null

  return (
    <div className="space-y-px">
      {visible.map((b) => (
        <div key={b.key} className="flex items-center gap-3 bg-blue-50 px-4 py-2 text-sm text-blue-900">
          <span>🔔 {b.text}</span>
          {b.external ? (
            <a
              href={b.link}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 rounded bg-blue-600 px-2.5 py-0.5 text-xs font-medium text-white hover:bg-blue-700"
            >
              <Video size={12} aria-hidden /> {b.cta}
            </a>
          ) : (
            <Link to={b.link} className="rounded bg-blue-600 px-2.5 py-0.5 text-xs font-medium text-white hover:bg-blue-700">
              {b.cta}
            </Link>
          )}
          <button
            onClick={() => {
              storageSet(`dismissed:${b.key}`, '1')
              force((n) => n + 1)
            }}
            className="ml-auto text-blue-700 hover:underline"
          >
            Bugünlük kapat
          </button>
        </div>
      ))}
    </div>
  )
}
