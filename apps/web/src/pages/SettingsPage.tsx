import { useEffect, useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import type { UserSettings, UserSettingsUpdate } from '../lib/types'
import { usePermissions, useSetPermission, type Permission } from '../api/assistant'

const MODE_LABEL: Record<Permission['mode'], string> = {
  ask: 'Bana sor',
  auto: 'Otomatik yap',
  never: 'Asla yapma',
}

/** AI'in hangi islemleri sormadan yapabilecegi: kullanici karar verir. */
function AssistantPermissions() {
  const perms = usePermissions()
  const set = useSetPermission()
  return (
    <section className="mt-6 space-y-3 rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
      <h2 className="font-medium">Asistan izinleri</h2>
      <p className="text-sm text-slate-500">
        Asistan bir işlem yapmak istediğinde ne olsun? “Bana sor” seçiliyse sohbette onay kartı çıkar.
      </p>
      {perms.error && <p className="text-sm text-red-600">{perms.error.message} (asistan servisi çalışıyor mu?)</p>}
      {perms.data?.map((p) => (
        <label key={p.action_type} className="flex items-center justify-between gap-4 text-sm">
          <span>{p.label}</span>
          <select
            className="rounded-md border border-slate-300 px-2 py-1"
            value={p.mode}
            disabled={set.isPending}
            onChange={(e) => set.mutate({ actionType: p.action_type, mode: e.target.value as Permission['mode'] })}
          >
            {(Object.keys(MODE_LABEL) as Permission['mode'][]).map((m) => (
              <option key={m} value={m}>{MODE_LABEL[m]}</option>
            ))}
          </select>
        </label>
      ))}
    </section>
  )
}

const toInput = (t: string | null | undefined) => (t ? t.slice(0, 5) : '')

/** Tarayici bildirim izni (hatirlaticilar uygulama aciktayken bildirim olarak da gelir). */
function NotificationPermission() {
  const supported = typeof window !== 'undefined' && 'Notification' in window
  const [perm, setPerm] = useState(supported ? Notification.permission : 'denied')
  if (!supported) return <p className="text-xs text-slate-400">Bu tarayıcı bildirimleri desteklemiyor.</p>
  return (
    <div className="flex items-center justify-between gap-4 text-sm">
      <span>
        Tarayıcı bildirimleri{' '}
        <span className="text-xs text-slate-400">(uygulama açıkken çalışır)</span>
      </span>
      {perm === 'granted' ? (
        <span className="text-green-600">Açık ✓</span>
      ) : perm === 'denied' ? (
        <span className="text-xs text-slate-500">Engellendi — tarayıcı ayarlarından izin ver</span>
      ) : (
        <button
          type="button"
          onClick={() => Notification.requestPermission().then(setPerm)}
          className="rounded-md bg-slate-200 px-3 py-1"
        >
          İzin ver
        </button>
      )}
    </div>
  )
}

export default function SettingsPage() {
  const qc = useQueryClient()
  const settings = useQuery({ queryKey: ['settings'], queryFn: () => api<UserSettings>('/settings/') })
  const save = useMutation({
    mutationFn: (data: UserSettingsUpdate) =>
      api<UserSettings>('/settings/', { method: 'PUT', body: JSON.stringify(data) }),
    onSuccess: (data) => qc.setQueryData(['settings'], data),
  })

  const [planning, setPlanning] = useState('')
  const [review, setReview] = useState('')
  const [reminders, setReminders] = useState(true)

  useEffect(() => {
    if (!settings.data) return
    setPlanning(toInput(settings.data.planning_time))
    setReview(toInput(settings.data.review_time))
    setReminders(settings.data.reminders_enabled)
  }, [settings.data])

  function submit(e: FormEvent) {
    e.preventDefault()
    save.mutate({
      planning_time: planning ? `${planning}:00` : null,
      review_time: review ? `${review}:00` : null,
      reminders_enabled: reminders,
    })
  }

  return (
    <div className="mx-auto w-full max-w-xl p-6">
      <h1 className="mb-6 text-2xl font-semibold">Ayarlar</h1>
      {settings.data && (
        <form onSubmit={submit} className="space-y-4 rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
          <p className="text-sm text-slate-500">
            Günü ne zaman planlamak ve ne zaman değerlendirmek istediğini seç. Bu saatlerde
            uygulama içinde ve (izin verirsen) tarayıcı bildirimiyle hatırlatma yapılır.
          </p>
          <label className="flex items-center justify-between gap-4">
            <span>Planlama saati</span>
            <input type="time" className="rounded-md border border-slate-300 px-2 py-1" value={planning} onChange={(e) => setPlanning(e.target.value)} />
          </label>
          <label className="flex items-center justify-between gap-4">
            <span>Gün sonu değerlendirme saati</span>
            <input type="time" className="rounded-md border border-slate-300 px-2 py-1" value={review} onChange={(e) => setReview(e.target.value)} />
          </label>
          <label className="flex items-center justify-between gap-4">
            <span>Hatırlatmalar</span>
            <input type="checkbox" checked={reminders} onChange={(e) => setReminders(e.target.checked)} />
          </label>
          <NotificationPermission />
          <p className="text-xs text-slate-400">Saat dilimi: {settings.data.timezone}</p>
          <div className="flex items-center justify-end gap-3">
            {save.isSuccess && <span className="text-sm text-green-600">Kaydedildi</span>}
            {save.error && <span className="text-sm text-red-600">{save.error.message}</span>}
            <button disabled={save.isPending} className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
              Kaydet
            </button>
          </div>
        </form>
      )}
      <AssistantPermissions />
    </div>
  )
}
