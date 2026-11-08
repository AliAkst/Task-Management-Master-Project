import { useEffect, useState, type FormEvent } from 'react'
import { ArrowRight, Check, Contrast, Plus, Timer, X, type LucideIcon } from 'lucide-react'
import { shiftDay, useDayPlanMutations } from '../api/dayPlans'
import { formatDuration } from '../lib/format'
import type { BoardWithCounts, DayPlan, ItemOutcome, PlanSuggestion } from '../lib/types'

// Sonuc renkleri durum bildirir (yapildi/kismen/yapilmadi/ertelendi); her biri ikon + yaziyla
const OUTCOMES: { value: ItemOutcome; label: string; icon: LucideIcon; on: string }[] = [
  { value: 'done', label: 'Yapıldı', icon: Check, on: 'bg-green-700 text-white' },
  { value: 'partial', label: 'Kısmen', icon: Contrast, on: 'bg-amber-600 text-white' },
  { value: 'not_done', label: 'Yapılmadı', icon: X, on: 'bg-red-700 text-white' },
  { value: 'postponed', label: 'Ertele', icon: ArrowRight, on: 'bg-blue-700 text-white' },
]
// 1-5 olcegi sozcukle: emoji yerine ne secildigi okunur
const MOODS = ['Çok kötü', 'Kötü', 'İdare eder', 'İyi', 'Çok iyi']
const ENERGY = ['Bitkin', 'Düşük', 'Orta', 'Yüksek', 'Çok yüksek']

interface ItemState {
  outcome: ItemOutcome | null
  reason: string
  postponed_to: string
}

/** 1-5 olcek: numara + sozcuk; tekrar tiklamak secimi kaldirir. */
function Scale({ label, words, value, onChange }: { label: string; words: string[]; value: number | null; onChange: (v: number | null) => void }) {
  return (
    <fieldset>
      <legend className="mb-1.5 text-[15px] font-semibold">{label}</legend>
      <div className="grid grid-cols-5 gap-1" role="radiogroup" aria-label={label}>
        {words.map((w, idx) => {
          const v = idx + 1
          const on = value === v
          return (
            <button
              type="button"
              key={w}
              role="radio"
              aria-checked={on}
              onClick={() => onChange(on ? null : v)}
              className={`flex flex-col items-center rounded-md border px-1 py-1.5 leading-tight ${
                on ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-white text-slate-700 hover:border-slate-400'
              }`}
            >
              <span className="font-display text-[18px] font-[650] tabular-nums">{v}</span>
              <span className={`text-[11px] ${on ? 'text-slate-200' : 'text-slate-500'}`}>{w}</span>
            </button>
          )
        })}
      </div>
    </fieldset>
  )
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
      <li key={i.id} className="relative py-3 pl-4">
        <span aria-hidden className="absolute inset-y-2 left-0 w-1 rounded-full" style={{ backgroundColor: board?.color ?? 'var(--color-slate-300)' }} />
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <div className="min-w-48 flex-1">
            <p className="text-[16px] leading-snug">{i.title}</p>
            {(tracked > 0 || i.planned_minutes != null) && (
              <p className="mt-0.5 inline-flex items-center gap-1 text-[13px] text-slate-500 tabular-nums">
                <Timer size={13} aria-hidden />
                {tracked > 0 ? formatDuration(tracked) : 'süre yok'}
                {i.planned_minutes != null && ` / ${formatDuration(i.planned_minutes * 60)} planlandı`}
              </p>
            )}
          </div>
          <div className="flex gap-1" role="radiogroup" aria-label={`${i.title} sonucu`}>
            {OUTCOMES.map((o) => {
              const on = st.outcome === o.value
              const Icon = o.icon
              return (
                <button
                  type="button"
                  key={o.value}
                  role="radio"
                  aria-checked={on}
                  onClick={() => set(i.id, { outcome: o.value })}
                  className={`inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-[13px] ${
                    on ? o.on : 'bg-white text-slate-700 ring-1 ring-slate-200 hover:ring-slate-400'
                  }`}
                >
                  <Icon size={13} strokeWidth={2.25} aria-hidden />
                  {o.label}
                </button>
              )
            })}
          </div>
        </div>
        {(st.outcome === 'not_done' || st.outcome === 'postponed' || st.outcome === 'partial') && (
          <div className="mt-2 flex flex-wrap gap-2">
            <input
              className="min-w-56 flex-1 rounded-md border border-slate-300 px-2 py-1 text-[14px]"
              placeholder="Neden? (asistan zamanla bu kalıpları öğrenir)"
              maxLength={2000}
              value={st.reason}
              onChange={(e) => set(i.id, { reason: e.target.value })}
            />
            {st.outcome === 'postponed' && (
              <input
                type="date"
                aria-label="Ertelenen gün"
                className="rounded-md border border-slate-300 px-2 text-[14px]"
                min={shiftDay(day, 1)}
                value={st.postponed_to}
                onChange={(e) => set(i.id, { postponed_to: e.target.value })}
              />
            )}
          </div>
        )}
      </li>
    )
  }

  return (
    <form onSubmit={submit} className="grid gap-x-12 gap-y-10 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="min-w-0 space-y-10">
        <section>
          <div className="flex items-baseline justify-between gap-3">
            <h2 className="text-[22px]">Planladıkların</h2>
            {planned.length > 0 && (
              <span className={`text-[14px] ${missing > 0 ? 'text-amber-800' : 'text-slate-500'}`}>
                {missing > 0 ? `${missing} madde işaretlenmedi` : 'Hepsi işaretlendi'}
              </span>
            )}
          </div>
          {planned.length === 0 ? (
            <p className="mt-2 text-[15px] text-slate-600">Bu gün için plan yapılmamış. Yaptıklarını aşağıya ekleyebilirsin.</p>
          ) : (
            <ul className="mt-2 divide-y divide-slate-200 border-y border-slate-200">{planned.map(row)}</ul>
          )}
        </section>

        <section>
          <h2 className="text-[22px]">Plansız yaptıkların</h2>
          <p className="mt-1 text-[15px] text-slate-600">Kronometresi çalışan ama planda olmayan kartlar kendiliğinden geldi.</p>
          <ul className="mt-2 divide-y divide-slate-200 border-t border-slate-200">
            {unplannedDone.map(row)}
            {workedExtra.map((s) => (
              <li key={s.card_id} className="flex items-center gap-3 py-2.5 text-[15px]">
                <input
                  type="checkbox"
                  aria-label={`${s.title} plansız iş olarak eklensin`}
                  checked={includeWorked.has(s.card_id!)}
                  onChange={(e) =>
                    setIncludeWorked((prev) => {
                      const n = new Set(prev)
                      if (e.target.checked) n.add(s.card_id!)
                      else n.delete(s.card_id!)
                      return n
                    })
                  }
                />
                <span className="flex-1">{s.title}</span>
                <span className="inline-flex items-center gap-1 text-[13px] text-slate-500 tabular-nums">
                  <Timer size={13} aria-hidden />
                  {formatDuration(s.tracked_sec)}
                </span>
              </li>
            ))}
            {extra.map((t, idx) => (
              <li key={idx} className="flex items-center gap-3 py-2.5 text-[15px]">
                <Check size={15} className="text-green-700" aria-label="Yapıldı" />
                <span className="flex-1">{t}</span>
                <button type="button" onClick={() => setExtra((x) => x.filter((_, j) => j !== idx))} className="rounded p-0.5 text-slate-400 hover:text-red-700" aria-label={`${t} maddesini çıkar`}>
                  <X size={15} aria-hidden />
                </button>
              </li>
            ))}
          </ul>
          <div className="mt-2 flex items-center gap-2 border-b border-slate-200 pb-2">
            <Plus size={16} className="text-slate-400" aria-hidden />
            <input
              className="flex-1 bg-transparent py-1 text-[15px] placeholder:text-slate-400 focus:outline-none"
              maxLength={200}
              aria-label="Başka ne yaptın?"
              placeholder="Başka ne yaptın? Yaz ve Enter'a bas"
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
      </div>

      {/* Sag sutun: gunun ozeti ve kaydet (PC'de kaydirirken gorunur kalir) */}
      <aside className="space-y-6 self-start lg:sticky lg:top-6 lg:border-l lg:border-slate-200 lg:pl-8">
        <h2 className="text-[22px]">Gün nasıldı?</h2>
        <Scale label="Ruh hâli" words={MOODS} value={mood} onChange={setMood} />
        <Scale label="Enerji" words={ENERGY} value={energy} onChange={setEnergy} />
        <label className="block">
          <span className="mb-1.5 block text-[15px] font-semibold">Günün notu</span>
          <textarea
            rows={5}
            className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-[15px]"
            placeholder="Ne iyi gitti, ne zorladı?"
            value={reflection}
            onChange={(e) => setReflection(e.target.value)}
          />
        </label>
        <div className="space-y-2">
          <button disabled={m.review.isPending} className="w-full rounded-md bg-slate-900 px-4 py-2.5 text-[15px] font-semibold text-white hover:bg-slate-700 disabled:opacity-50">
            {plan.status === 'reviewed' ? 'Değerlendirmeyi güncelle' : 'Günü değerlendir'}
          </button>
          <p className="text-center text-[14px]" aria-live="polite">
            {m.review.error ? (
              <span className="text-red-700">{m.review.error.message}</span>
            ) : m.review.isSuccess ? (
              <span className="text-green-700">Değerlendirme kaydedildi</span>
            ) : (
              <span className="text-slate-500">Tamamlanan kartlar kapanır, ertelenenler yarının önerilerine düşer.</span>
            )}
          </p>
        </div>
      </aside>
    </form>
  )
}
