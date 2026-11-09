import { Check, Hourglass, Play, Plus, Square, X } from 'lucide-react'
import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useDayPlanMutations } from '../api/dayPlans'
import { useActiveSession, useSessionMutations } from '../api/sessions'
import { formatDuration } from '../lib/format'
import type { BoardWithCounts, DayPlan, PlanSuggestion } from '../lib/types'

/** Plan maddesindeki kart icin kronometre: istedigin an basla / durdur. */
function PlayButton({ cardId, title }: { cardId: number; title: string }) {
  const active = useActiveSession()
  const m = useSessionMutations()
  const running = active.data?.card_id === cardId
  return (
    <button
      onClick={() => (running ? m.stop.mutate() : m.start.mutate(cardId))}
      disabled={m.start.isPending || m.stop.isPending}
      aria-label={running ? `${title} için kronometreyi durdur` : `${title} için çalışmaya başla`}
      title={running ? 'Durdur' : active.data ? 'Çalışan süre durur, bu kart başlar' : 'Çalışmaya başla'}
      className={`rounded p-1 ${running ? 'text-[var(--color-rec)]' : 'text-slate-400 hover:text-slate-900'} disabled:opacity-50`}
    >
      {running ? <Square size={13} fill="currentColor" aria-hidden /> : <Play size={14} aria-hidden />}
    </button>
  )
}

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
  next_in_chain: 'Sıradaki',
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
    <div className="grid gap-x-12 gap-y-10 lg:grid-cols-2">
      <section>
        <h2 className="text-[22px]">Öneriler</h2>
        <p className="mt-1 mb-4 text-[15px] text-slate-600">Takvimden, son tarihlerden ve ertelenenlerden toplandı. Plana eklemek için tıkla.</p>
        {grouped.length === 0 && <p className="text-[15px] text-slate-500">Bu gün için öneri yok; planı sağdan kendin yaz.</p>}
        {grouped.map((g) => (
          <div key={g.kind} className="mb-5">
            <h3 className="mb-1 text-[14px] font-semibold text-slate-700">{KIND_LABEL[g.kind]}</h3>
            <ul className="space-y-1">
              {g.items.map((s) => {
                const on = inDraft.has(keyOf(s))
                const board = s.board_id != null ? boards.get(s.board_id) : undefined
                return (
                  <li key={keyOf(s)}>
                    <button
                      onClick={() => toggle(s)}
                      aria-pressed={on}
                      className={`flex w-full items-center gap-2 rounded-md border border-l-4 px-2.5 py-2 text-left text-[15px] ${on ? 'border-blue-600 bg-blue-50' : 'border-slate-200 bg-surface hover:border-slate-400'}`}
                      style={{ borderLeftColor: board?.color ?? '#cbd5e1' }}
                    >
                      {on ? <Check size={15} className="shrink-0 text-blue-700" aria-hidden /> : <Plus size={15} className="shrink-0 text-slate-400" aria-hidden />}
                      <span className={`flex-1 ${s.blocked ? 'text-slate-500' : ''}`}>{s.title}</span>
                      {s.blocked && <span className="inline-flex items-center gap-0.5 text-[12px] text-amber-800"><Hourglass size={12} aria-hidden />Bekliyor</span>}
                      {s.planned_start && <span className="text-[13px] text-slate-600 tabular-nums">{timeFmt.format(new Date(s.planned_start))}</span>}
                      {s.planned_minutes != null && <span className="text-[13px] text-slate-500 tabular-nums">{formatDuration(s.planned_minutes * 60)}</span>}
                    </button>
                  </li>
                )
              })}
            </ul>
          </div>
        ))}
      </section>

      <section className="self-start lg:sticky lg:top-6 lg:border-l lg:border-slate-200 lg:pl-8">
        <div className="mb-3 flex items-baseline justify-between gap-3">
          <h2 className="text-[22px]">Planın</h2>
          <span className="text-[14px] text-slate-600 tabular-nums">{draft.length} madde, {formatDuration(total * 60)}</span>
        </div>
        <ul className="divide-y divide-slate-200 border-y border-slate-200">
          {draft.map((d) => (
            <li key={d.key} className="group flex items-center gap-2 py-2 text-[15px]">
              <span aria-hidden className="h-5 w-1 shrink-0 rounded-full" style={{ backgroundColor: d.board_id != null ? boards.get(d.board_id)?.color : 'var(--color-slate-300)' }} />
              <span className="flex-1">{d.title}</span>
              {d.card_id != null && <PlayButton cardId={d.card_id} title={d.title} />}
              {d.hint && <span className="text-[13px] text-slate-500">{d.hint}</span>}
              <input
                type="number"
                min={0}
                step={5}
                title="Planlanan dakika"
                aria-label={`${d.title} için planlanan dakika`}
                className="w-16 rounded border border-slate-300 bg-surface px-1.5 py-0.5 text-right text-[13px] tabular-nums"
                value={d.planned_minutes ?? ''}
                placeholder="dk"
                onChange={(e) => {
                  const v = e.target.value === '' ? null : Number(e.target.value)
                  update((all) => all.map((x) => (x.key === d.key ? { ...x, planned_minutes: v } : x)))
                }}
              />
              <button onClick={() => update((all) => all.filter((x) => x.key !== d.key))} className="rounded p-0.5 text-slate-400 hover:text-red-700" aria-label={`${d.title} plandan çıkar`}><X size={15} aria-hidden /></button>
            </li>
          ))}
        </ul>
        {draft.length === 0 && <p className="py-3 text-[15px] text-slate-500">Henüz madde yok. Önerilerden ekle ya da aşağıya yaz.</p>}
        <form onSubmit={addFree} className="mt-2 flex items-center gap-2 border-b border-slate-200 pb-2">
          <Plus size={16} className="text-slate-400" aria-hidden />
          <input className="flex-1 bg-transparent py-1 text-[15px] placeholder:text-slate-400 focus:outline-none" maxLength={200} aria-label="Karta bağlı olmayan madde" placeholder="Karta bağlı olmayan bir madde yaz" value={free} onChange={(e) => setFree(e.target.value)} />
        </form>
        <div className="mt-4 flex items-center justify-end gap-3">
          {m.save.isSuccess && !dirty && <span className="text-[14px] text-green-700">Plan kaydedildi</span>}
          {m.save.error && <span className="text-[14px] text-red-700">{m.save.error.message}</span>}
          <button onClick={save} disabled={m.save.isPending || (!dirty && plan.exists)} className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-on-ink disabled:opacity-50">
            Planı kaydet
          </button>
        </div>
      </section>
    </div>
  )
}
