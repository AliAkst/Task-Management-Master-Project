import { useEffect, useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import type { UserSettings, UserSettingsUpdate } from '../lib/types'

const toInput = (t: string | null | undefined) => (t ? t.slice(0, 5) : '')

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
            Günü ne zaman planlamak ve ne zaman değerlendirmek istediğini seç. Hatırlatmalar bu
            saatlere göre gönderilecek (Faz 3b).
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
    </div>
  )
}
