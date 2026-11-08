import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { localDay, shiftDay, useDayPlan } from '../api/dayPlans'
import { api } from '../lib/api'
import type { UserSettings } from '../lib/types'

/**
 * Planlama / gun sonu hatirlaticilari.
 * Uygulama acikken calisir: saat geldiyse ve is yapilmadiysa uygulama ici serit +
 * (izin verildiyse) gunde bir kez tarayici bildirimi. Tarayici kapaliyken bildirim
 * gelmez; bunun icin sunucu tarafli push gerekir (ileride, Docker kurulunca).
 */

const EVENING_PLANNING_HOUR = 15 // bu saatten sonraki planlama -> ertesi gunu planlar

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

  if (!settings.data?.reminders_enabled) return null
  const nowMin = now.getHours() * 60 + now.getMinutes()
  const reviewTime = minutesOf(settings.data.review_time)

  const banners: { key: string; text: string; link: string; cta: string }[] = []

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
          <Link to={b.link} className="rounded bg-blue-600 px-2.5 py-0.5 text-xs font-medium text-white hover:bg-blue-700">
            {b.cta}
          </Link>
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
