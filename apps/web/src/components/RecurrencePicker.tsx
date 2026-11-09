import { useState } from 'react'
import { WEEKDAYS, buildRule, describeRule, parseRule, type DayCode, type Mode, type RuleState } from '../lib/rrule'

const MODES: { value: Mode; label: string }[] = [
  { value: 'none', label: 'Tekrarlanmaz' },
  { value: 'daily', label: 'Her gün' },
  { value: 'weekdays', label: 'Hafta içi her gün' },
  { value: 'weekly', label: 'Haftanın belirli günleri' },
  { value: 'monthly', label: 'Her ay' },
  { value: 'yearly', label: 'Her yıl' },
  { value: 'custom', label: 'Özel kural (RRULE)' },
]

/**
 * Tekrar secici (etkinlik ve kart icin ortak). Her degisiklikte kurali
 * (ya da null) bildirir; `instant` ise (kart) kural degisince hemen kaydedilir,
 * ozel kural yazilirken ise alan birakilinca.
 */
export default function RecurrencePicker({
  value,
  onChange,
  startDay,
  label = 'Tekrar',
  inputClass = 'w-full rounded-md border border-slate-300 bg-surface px-2 py-1.5 text-sm',
}: {
  value: string | null
  onChange: (rule: string | null) => void
  startDay: DayCode
  label?: string
  inputClass?: string
}) {
  const [s, setS] = useState<RuleState>(() => parseRule(value, startDay))
  const update = (patch: Partial<RuleState>, emit = true) => {
    const next = { ...s, ...patch }
    setS(next)
    if (emit && next.mode !== 'custom') onChange(buildRule(next))
  }
  const toggleDay = (code: DayCode) => {
    const days = s.days.includes(code) ? s.days.filter((d) => d !== code) : [...s.days, code]
    if (days.length) update({ days })
  }
  const summary = describeRule(buildRule(s))

  return (
    <div className="space-y-2">
      <label className="block space-y-1">
        <span className="text-[13px] text-slate-600">{label}</span>
        <select
          className={inputClass}
          value={s.mode}
          onChange={(e) => update({ mode: e.target.value as Mode }, e.target.value !== 'custom')}
        >
          {MODES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
        </select>
      </label>

      {s.mode === 'weekly' && (
        <div className="flex flex-wrap gap-1" role="group" aria-label="Tekrar günleri">
          {WEEKDAYS.map((d) => {
            const on = s.days.includes(d.code)
            return (
              <button
                type="button"
                key={d.code}
                aria-pressed={on}
                title={d.long}
                onClick={() => toggleDay(d.code)}
                className={`w-10 rounded-md py-1 text-[13px] ${on ? 'bg-slate-900 text-on-ink' : 'text-slate-700 ring-1 ring-slate-300 hover:ring-slate-900'}`}
              >
                {d.short}
              </button>
            )
          })}
        </div>
      )}

      {s.mode === 'custom' && (
        <input
          className={`${inputClass} font-mono`}
          placeholder="FREQ=WEEKLY;INTERVAL=2;BYDAY=TU"
          value={s.raw}
          maxLength={500}
          onChange={(e) => setS({ ...s, raw: e.target.value })}
          onBlur={() => onChange(buildRule(s))}
          aria-label="Özel tekrar kuralı"
        />
      )}

      {s.mode !== 'none' && s.mode !== 'custom' && (
        <label className="flex items-center gap-2 text-[13px] text-slate-600">
          Bitiş
          <input
            type="date"
            className="rounded-md border border-slate-300 bg-surface px-2 py-1 text-[13px]"
            value={s.until}
            onChange={(e) => update({ until: e.target.value })}
          />
          {s.until && (
            <button type="button" className="text-slate-500 hover:underline" onClick={() => update({ until: '' })}>
              Kaldır
            </button>
          )}
        </label>
      )}

      {summary && <p className="text-[13px] text-slate-600">{summary}</p>}
    </div>
  )
}
