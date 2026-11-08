import { useEffect, useState, type FormEvent } from 'react'
import { shiftDay, useDayPlanMutations } from '../api/dayPlans'
import { formatDuration } from '../lib/format'
import type { BoardWithCounts, DayPlan, ItemOutcome, PlanSuggestion } from '../lib/types'

const OUTCOMES: { value: ItemOutcome; label: string; cls: string }[] = [
  { value: 'done', label: '✓ Yapıldı', cls: 'bg-green-600 text-white' },
  { value: 'partial', label: '◐ Kısmen', cls: 'bg-amber-500 text-white' },
  { value: 'not_done', label: '✗ Yapılmadı', cls: 'bg-red-600 text-white' },
  { value: 'postponed', label: '→ Ertele', cls: 'bg-blue-600 text-white' },
]
const MOODS = ['😞', '😕', '😐', '🙂', '😄']
const ENERGY = ['🪫', '🔋', '🔋🔋', '⚡', '⚡⚡']

interface ItemState {
  outcome: ItemOutcome | null
  reason: string
  postponed_to: string
}

export default function DayReviewForm({
  day,
  plan,
  suggestions,
  boards,
}: {
  day: string
  plan: DayPlan
  suggestions: PlanSuggestion[]
  boards: Map<number, BoardWithCounts>
}) {
  const m = useDayPlanMutations(day)
  const planned = plan.items.filter((i) => i.was_planned)
  const unplannedDone = plan.items.filter((i) => !i.was_planned)
  // Planda olmayan ama o gun uzerinde calisilan kartlar -> plansiz is adayi
  const workedExtra = suggestions.filter(
    (s) => s.kind === 'worked' && !plan.items.some((i) => i.card_id === s.card_id),
  )

  const [state, setState] = useState<Record<number, ItemState>>({})
  const [includeWorked, setIncludeWorked] = useState<Set<number>>(new Set())
  const [extra, setExtra] = useState<string[]>([])
  const [extraInput, setExtraInput] = useState('')
  const [mood, setMood] = useState<number | null>(null)
  const [energy, setEnergy] = useState<number | null>(null)
  const [reflection, setReflection] = useState('')

  useEffect(() => {
    const next: Record<number, ItemState> = {}
    for (const i of plan.items) {
      next[i.id] = {
        // Kart zaten tamamlanmissa varsayilan "Yapildi"
        outcome: i.outcome ?? (i.card_status === 'completed' ? 'done' : null),
        reason: i.reason ?? '',
        postponed_to: i.postponed_to ?? shiftDay(day, 1),
      }
    }
    setState(next)
    setMood(plan.mood)
    setEnergy(plan.energy)
    setReflection(plan.reflection ?? '')
  }, [plan, day])

  useEffect(() => {
    // Calisilan kartlar varsayilan olarak dahil
    setIncludeWorked(new Set(workedExtra.map((s) => s.card_id!)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [suggestions.length, plan.items.length])

  const set = (id: number, patch: Partial<ItemState>) =>
    setState((s) => ({ ...s, [id]: { ...s[id], ...patch } }))

  const missing = planned.filter((i) => !state[i.id]?.outcome).length

  function submit(e: FormEvent) {
    e.preventDefault()
    m.review.mutate({
      mood,
      energy,
      reflection: reflection.trim() || null,
      items: [...planned, ...unplannedDone]
        .filter((i) => state[i.id]?.outcome)
        .map((i) => ({
          id: i.id,
          outcome: state[i.id].outcome!,
          reason: state[i.id].reason.trim() || null,
          postponed_to: state[i.id].outcome === 'postponed' ? state[i.id].postponed_to : null,
        })),
      unplanned: [
        ...workedExtra
          .filter((s) => includeWorked.has(s.card_id!))
          .map((s) => ({ card_id: s.card_id, outcome: 'done' as const })),
        ...extra.map((title) => ({ title, outcome: 'done' as const })),
      ],
    })
  }

  const row = (i: DayPlan['items'][number]) => {
    const st = state[i.id]
    if (!st) return null
    const board = i.board_id != null ? boards.get(i.board_id) : undefined
    const tracked = i.tracked_today_sec || i.tracked_sec
    return (
      <li key={i.id} className="rounded-md border-l-4 bg-slate-50 p-2" style={{ borderLeftColor: board?.color ?? '#cbd5e1' }}>
        <div className="flex flex-wrap items-center gap-2">
          <span className="min-w-40 flex-1 text-sm">{i.title}</span>
          <span className="text-xs text-slate-500">
            {tracked > 0 && `⏲ ${formatDuration(tracked)}`}
            {i.planned_minutes != null && ` / ${formatDuration(i.planned_minutes * 60)} plan`}
          </span>
          <div className="flex gap-1">
            {OUTCOMES.map((o) => (
              <button
                type="button"
                key={o.value}
                onClick={() => set(i.id, { outcome: o.value })}
                className={`rounded px-2 py-0.5 text-xs ${st.outcome === o.value ? o.cls : 'bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-100'}`}
              >
                {o.label}
              </button>
            ))}
          </div>
        </div>
        {(st.outcome === 'not_done' || st.outcome === 'postponed' || st.outcome === 'partial') && (
          <div className="mt-1.5 flex flex-wrap gap-2">
            <input
              className="flex-1 rounded border border-slate-200 px-2 py-0.5 text-xs"
              placeholder="Neden? (AI ileride bu kalıpları öğrenecek)"
              maxLength={2000}
              value={st.reason}
              onChange={(e) => set(i.id, { reason: e.target.value })}
            />
            {st.outcome === 'postponed' && (
              <input type="date" className="rounded border border-slate-200 px-1 text-xs" min={shiftDay(day, 1)} value={st.postponed_to} onChange={(e) => set(i.id, { postponed_to: e.target.value })} />
            )}
          </div>
        )}
      </li>
    )
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <section className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
        <h2 className="mb-3 font-medium">Planladıkların</h2>
        {planned.length === 0 && <p className="text-sm text-slate-400">Bu gün için plan yapılmamış. Aşağıya yaptıklarını ekleyebilirsin.</p>}
        <ul className="space-y-1.5">{planned.map(row)}</ul>
      </section>

      <section className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
        <h2 className="mb-1 font-medium">Plansız yaptıkların</h2>
        <p className="mb-2 text-xs text-slate-500">Kronometresi çalışan ama planda olmayan kartlar otomatik geldi.</p>
        <ul className="space-y-1.5">
          {unplannedDone.map(row)}
          {workedExtra.map((s) => (
            <li key={s.card_id} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={includeWorked.has(s.card_id!)}
                onChange={(e) =>
                  setIncludeWorked((set) => {
                    const n = new Set(set)
                    if (e.target.checked) n.add(s.card_id!)
                    else n.delete(s.card_id!)
                    return n
                  })
                }
              />
              <span className="flex-1">{s.title}</span>
              <span className="text-xs text-slate-500">⏲ {formatDuration(s.tracked_sec)}</span>
            </li>
          ))}
          {extra.map((t, idx) => (
            <li key={idx} className="flex items-center gap-2 text-sm">
              <span className="text-green-600">✓</span>
              <span className="flex-1">{t}</span>
              <button type="button" onClick={() => setExtra((x) => x.filter((_, j) => j !== idx))} className="text-slate-400 hover:text-red-600">×</button>
            </li>
          ))}
        </ul>
        <div className="mt-2 flex gap-2">
          <input
            className="flex-1 rounded-md border border-slate-300 px-2 py-1 text-sm"
            maxLength={200}
            placeholder="+ Başka ne yaptın?"
            value={extraInput}
            onChange={(e) => setExtraInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && extraInput.trim()) {
                e.preventDefault()
                setExtra((x) => [...x, extraInput.trim()])
                setExtraInput('')
              }
            }}
          />
        </div>
      </section>

      <section className="grid gap-4 rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200 md:grid-cols-2">
        <div>
          <h3 className="mb-2 text-sm font-medium">Ruh hâli</h3>
          <div className="flex gap-1">
            {MOODS.map((e, idx) => (
              <button type="button" key={idx} title={`${idx + 1}/5`} onClick={() => setMood(mood === idx + 1 ? null : idx + 1)} className={`rounded-md px-2 py-1 text-xl ${mood === idx + 1 ? 'bg-slate-200 ring-2 ring-slate-400' : 'opacity-50 hover:opacity-100'}`}>{e}</button>
            ))}
          </div>
          <h3 className="mt-3 mb-2 text-sm font-medium">Enerji</h3>
          <div className="flex gap-1">
            {ENERGY.map((e, idx) => (
              <button type="button" key={idx} title={`${idx + 1}/5`} onClick={() => setEnergy(energy === idx + 1 ? null : idx + 1)} className={`rounded-md px-2 py-1 text-sm ${energy === idx + 1 ? 'bg-slate-200 ring-2 ring-slate-400' : 'opacity-50 hover:opacity-100'}`}>{e}</button>
            ))}
          </div>
        </div>
        <label className="block">
          <span className="mb-2 block text-sm font-medium">Günün notu</span>
          <textarea rows={4} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" placeholder="Bugün nasıl geçti? Ne iyi gitti, ne zorladı?" value={reflection} onChange={(e) => setReflection(e.target.value)} />
        </label>
      </section>

      <div className="flex items-center justify-end gap-3">
        {missing > 0 && <span className="text-sm text-amber-600">{missing} madde işaretlenmedi</span>}
        {m.review.error && <span className="text-sm text-red-600">{m.review.error.message}</span>}
        {m.review.isSuccess && <span className="text-sm text-green-600">Kaydedildi ✓</span>}
        <button disabled={m.review.isPending} className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
          {plan.status === 'reviewed' ? 'Değerlendirmeyi güncelle' : 'Günü değerlendir'}
        </button>
      </div>
    </form>
  )
}
