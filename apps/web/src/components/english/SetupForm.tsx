import { useState, type FormEvent } from 'react'
import {
  FOCUS_LABELS,
  LEVELS,
  useSaveProfile,
  type EnglishProfile,
  type FocusArea,
  type Level,
} from '../../api/english'
import { ApiError } from '../../lib/api'

const FOCUS = Object.keys(FOCUS_LABELS) as FocusArea[]
const field = 'rounded-md border border-slate-300 bg-surface px-2 py-1.5 text-[15px]'

/** İlk kurulum ve Ayarlar sekmesindeki profil formu. */
export default function SetupForm({
  initial,
  submitLabel = 'Başla',
  onSaved,
}: {
  initial?: EnglishProfile | null
  submitLabel?: string
  onSaved?: () => void
}) {
  const save = useSaveProfile()
  const [target, setTarget] = useState<Level>(initial?.target_level ?? 'B2')
  const [current, setCurrent] = useState<Level | ''>(initial?.current_level ?? '')
  const [minutes, setMinutes] = useState(initial?.daily_minutes ?? 15)
  const [focus, setFocus] = useState<FocusArea[]>(initial?.focus ?? FOCUS)
  const [saved, setSaved] = useState(false)

  const minutesOk = Number.isInteger(minutes) && minutes >= 5 && minutes <= 120
  const canSubmit = minutesOk && focus.length > 0 && !save.isPending

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return
    setSaved(false)
    save.mutate(
      { target_level: target, current_level: current || null, daily_minutes: minutes, focus },
      {
        onSuccess: () => {
          setSaved(true)
          onSaved?.()
        },
      },
    )
  }

  const toggle = (f: FocusArea) =>
    setFocus((cur) => (cur.includes(f) ? cur.filter((x) => x !== f) : [...cur, f]))

  return (
    <form onSubmit={submit} className="max-w-md space-y-4">
      <label className="block">
        <span className="mb-1 block text-sm font-semibold">Hedef seviye</span>
        <select className={field} value={target} onChange={(e) => setTarget(e.target.value as Level)}>
          {LEVELS.map((l) => (
            <option key={l}>{l}</option>
          ))}
        </select>
      </label>
      <label className="block">
        <span className="mb-1 block text-sm font-semibold">Şu anki seviye</span>
        <select className={field} value={current} onChange={(e) => setCurrent(e.target.value as Level | '')}>
          <option value="">Bilmiyorum</option>
          {LEVELS.map((l) => (
            <option key={l}>{l}</option>
          ))}
        </select>
      </label>
      <label className="block">
        <span className="mb-1 block text-sm font-semibold">Günlük dakika (5–120)</span>
        <input
          type="number"
          min={5}
          max={120}
          className={`${field} w-24`}
          value={Number.isNaN(minutes) ? '' : minutes}
          onChange={(e) => setMinutes(e.target.value === '' ? NaN : Number(e.target.value))}
        />
      </label>
      <fieldset>
        <legend className="mb-1 text-sm font-semibold">Odak</legend>
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          {FOCUS.map((f) => (
            <label key={f} className="flex items-center gap-1.5 text-[15px]">
              <input type="checkbox" checked={focus.includes(f)} onChange={() => toggle(f)} />
              {FOCUS_LABELS[f]}
            </label>
          ))}
        </div>
      </fieldset>
      {save.isError && (
        <p role="alert" className="text-sm text-red-700">
          {save.error instanceof ApiError ? save.error.message : 'Kaydedilemedi, tekrar dene'}
        </p>
      )}
      {saved && !save.isPending && <p className="text-sm text-slate-600">Kaydedildi.</p>}
      <button
        disabled={!canSubmit}
        className="rounded-md bg-slate-900 px-4 py-1.5 text-[15px] text-on-ink disabled:opacity-40"
      >
        {save.isPending ? 'Kaydediliyor…' : submitLabel}
      </button>
    </form>
  )
}
