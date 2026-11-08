import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useDayPlanMutations } from '../api/dayPlans'
import { formatDuration } from '../lib/format'
import type { BoardWithCounts, DayPlan, PlanSuggestion } from '../lib/types'

/** Plandaki bir madde (kaydedilmeden onceki taslak). */
interface Draft {
  key: string
  card_id: number | null
  event_id: number | null
  title: string
  board_id: number | null
  planned_minutes: number | null
  hint?: string
}

const KIND_LABEL: Record<PlanSuggestion['kind'], string> = {
  event: 'Takvimde',
  carry_over: 'Ertelenen',
  due: 'Son tarihi bugün',
  overdue: 'Gecikmiş',
  in_progress: 'Devam eden',
  worked: 'Üzerinde çalışılan',
}

const keyOf = (s: { card_id: number | null; event_id: number | null; title: string }) =>
  s.event_id != null ? `e${s.event_id}` : s.card_id != null ? `c${s.card_id}` : `t${s.title}`

const timeFmt = new Intl.DateTimeFormat('tr-TR', { hour: '2-digit', minute: '2-digit' })

export default function PlanEditor({
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
  const [draft, setDraft] = useState<Draft[]>([])
  const [free, setFree] = useState('')
  const [dirty, setDirty] = useState(false)

  // Sunucudaki plan degisince taslagi ondan kur
  useEffect(() => {
    setDraft(
      plan.items
        .filter((i) => i.was_planned)
        .map((i) => ({
          key: keyOf(i),
          card_id: i.card_id,
          event_id: i.event_id,
          title: i.title,
          board_id: i.board_id,
          planned_minutes: i.planned_minutes,
          hint: i.planned_start ? timeFmt.format(new Date(i.planned_start)) : undefined,
        })),
    )
    setDirty(false)
  }, [plan])

  const inDraft = useMemo(() => new Set(draft.map((d) => d.key)), [draft])
  const total = draft.reduce((s, d) => s + (d.planned_minutes ?? 0), 0)

  const update = (fn: (d: Draft[]) => Draft[]) => {
    setDraft(fn)
    setDirty(true)
  }

  function toggle(s: PlanSuggestion) {
    const key = keyOf(s)
    if (inDraft.has(key)) return update((d) => d.filter((x) => x.key !== key))
    update((d) => [
      ...d,
      {
        key,
        card_id: s.card_id,
        event_id: s.event_id,
        title: s.title,
        board_id: s.board_id,
        planned_minutes: s.planned_minutes,
        hint: s.planned_start ? timeFmt.format(new Date(s.planned_start)) : undefined,
      },
    ])
  }

  function addFree(e: FormEvent) {
    e.preventDefault()
    const title = free.trim()
    if (!title) return
    update((d) => [...d, { key: `t${title}${Date.now()}`, card_id: null, event_id: null, title, board_id: null, planned_minutes: null }])
    setFree('')
  }

  function save() {
    m.save.mutate(
      draft.map((d) => ({
        card_id: d.card_id,
        event_id: d.event_id,
        title: d.card_id == null && d.event_id == null ? d.title : null,
        planned_minutes: d.planned_minutes,
      })),
    )
  }

  const grouped = (Object.keys(KIND_LABEL) as PlanSuggestion['kind'][])
    .map((kind) => ({ kind, items: suggestions.filter((s) => s.kind === kind) }))
    .filter((g) => g.items.length > 0)

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <section className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
        <h2 className="mb-1 font-medium">Öneriler</h2>
        <p className="mb-3 text-xs text-slate-500">Takvimden, son tarihlerden ve ertelenenlerden toplandı. Eklemek için tıkla.</p>
        {grouped.length === 0 && <p className="text-sm text-slate-400">Bu gün için öneri yok.</p>}
        {grouped.map((g) => (
          <div key={g.kind} className="mb-3">
            <h3 className="mb-1 text-[13px] text-slate-500">{KIND_LABEL[g.kind]}</h3>
            <ul className="space-y-1">
              {g.items.map((s) => {
                const on = inDraft.has(keyOf(s))
                const board = s.board_id != null ? boards.get(s.board_id) : undefined
                return (
                  <li key={keyOf(s)}>
                    <button
                      onClick={() => toggle(s)}
                      className={`flex w-full items-center gap-2 rounded-md border-l-4 px-2 py-1.5 text-left text-sm ${on ? 'bg-blue-50' : 'bg-slate-50 hover:bg-slate-100'}`}
                      style={{ borderLeftColor: board?.color ?? '#cbd5e1' }}
                    >
                      <span className={on ? 'text-blue-600' : 'text-slate-300'}>{on ? '✓' : '+'}</span>
                      <span className={`flex-1 ${s.blocked ? 'text-slate-400' : ''}`}>
                        {s.blocked && '⛓ '}
                        {s.title}
                      </span>
                      {s.planned_start && <span className="text-xs text-slate-500">{timeFmt.format(new Date(s.planned_start))}</span>}
                      {s.planned_minutes != null && <span className="text-xs text-slate-400">{formatDuration(s.planned_minutes * 60)}</span>}
                    </button>
                  </li>
                )
              })}
            </ul>
          </div>
        ))}
      </section>

      <section className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="font-medium">Planın</h2>
          <span className="text-sm text-slate-500">{draft.length} madde · {formatDuration(total * 60)}</span>
        </div>
        <ul className="space-y-1.5">
          {draft.map((d) => (
            <li key={d.key} className="group flex items-center gap-2 rounded-md bg-slate-50 px-2 py-1.5 text-sm">
              <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: d.board_id != null ? boards.get(d.board_id)?.color : '#cbd5e1' }} />
              <span className="flex-1">{d.title}</span>
              {d.hint && <span className="text-xs text-slate-500">{d.hint}</span>}
              <input
                type="number"
                min={0}
                step={5}
                title="Planlanan dakika"
                className="w-16 rounded border border-slate-200 bg-white px-1 py-0.5 text-right text-xs"
                value={d.planned_minutes ?? ''}
                placeholder="dk"
                onChange={(e) => {
                  const v = e.target.value === '' ? null : Number(e.target.value)
                  update((all) => all.map((x) => (x.key === d.key ? { ...x, planned_minutes: v } : x)))
                }}
              />
              <button onClick={() => update((all) => all.filter((x) => x.key !== d.key))} className="text-slate-400 hover:text-red-600" aria-label="Plandan çıkar">×</button>
            </li>
          ))}
        </ul>
        {draft.length === 0 && <p className="text-sm text-slate-400">Henüz madde yok. Önerilerden ekle ya da aşağıya yaz.</p>}
        <form onSubmit={addFree} className="mt-2">
          <input className="w-full rounded-md border border-slate-300 px-2 py-1 text-sm" maxLength={200} placeholder="+ Karta bağlı olmayan madde" value={free} onChange={(e) => setFree(e.target.value)} />
        </form>
        <div className="mt-4 flex items-center justify-end gap-3">
          {m.save.isSuccess && !dirty && <span className="text-sm text-green-600">Kaydedildi</span>}
          {m.save.error && <span className="text-sm text-red-600">{m.save.error.message}</span>}
          <button onClick={save} disabled={m.save.isPending || (!dirty && plan.exists)} className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
            Planı kaydet
          </button>
        </div>
      </section>
    </div>
  )
}
