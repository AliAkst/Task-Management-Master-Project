import { CalendarDays } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useCalendarMutations, useCardEvents } from '../api/calendar'
import { formatRange, fromLocalInput, toLocalInput } from '../lib/format'

/** Kart detayindaki "Takvimde" bolumu: karta ayrilmis zaman bloklari. */
export default function CardSchedule({
  cardId,
  estimatedMinutes,
}: {
  cardId: number
  estimatedMinutes: number | null
}) {
  const events = useCardEvents(cardId)
  const m = useCalendarMutations()
  const [adding, setAdding] = useState(false)
  const [start, setStart] = useState(() => {
    const d = new Date()
    d.setHours(d.getHours() + 1, 0, 0, 0) // bir sonraki tam saat
    return toLocalInput(d)
  })
  const [minutes, setMinutes] = useState(String(estimatedMinutes || 60))

  const now = Date.now()
  const upcoming = (events.data ?? []).filter((e) => new Date(e.end_at).getTime() >= now)
  const past = (events.data?.length ?? 0) - upcoming.length

  function submit(e: FormEvent) {
    e.preventDefault()
    const s = new Date(fromLocalInput(start))
    const end = new Date(s.getTime() + Math.max(5, Number(minutes) || 60) * 60_000)
    m.create.mutate(
      { card_id: cardId, start_at: s.toISOString(), end_at: end.toISOString() },
      { onSuccess: () => setAdding(false) },
    )
  }

  return (
    <div className="mt-7">
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <h3 className="text-[15px] font-semibold text-slate-900">Takvimde</h3>
        <button onClick={() => setAdding((a) => !a)} aria-expanded={adding} className="shrink-0 text-[13px] text-blue-700 hover:underline">
          Zaman ayır
        </button>
      </div>
      {adding && (
        <form onSubmit={submit} className="mb-2 flex flex-wrap items-end gap-2 rounded-md bg-slate-50 p-2 text-sm">
          <input type="datetime-local" required className="rounded border border-slate-300 px-2 py-1" value={start} onChange={(e) => setStart(e.target.value)} />
          <label className="flex items-center gap-1">
            <input type="number" min={5} step={5} className="w-20 rounded border border-slate-300 px-2 py-1" value={minutes} onChange={(e) => setMinutes(e.target.value)} />
            dk
          </label>
          <button disabled={m.create.isPending} className="rounded-md bg-slate-900 px-3 py-1 text-on-ink disabled:opacity-50">Ekle</button>
          {m.create.error && <span className="text-red-600">{m.create.error.message}</span>}
        </form>
      )}
      <ul className="space-y-1 text-sm">
        {upcoming.map((e) => (
          <li key={e.id} className="group flex items-center gap-2">
            <CalendarDays size={13} className="shrink-0 text-slate-400" aria-hidden />
            <span className="flex-1">{formatRange(e.start_at, e.end_at, e.all_day)}</span>
            <button
              onClick={() => m.remove.mutate(e.id)}
              className="text-xs text-slate-400 opacity-0 group-hover:opacity-100 hover:text-red-600"
            >
              Kaldır
            </button>
          </li>
        ))}
      </ul>
      {upcoming.length === 0 && !adding && (
        <p className="text-[13px] text-slate-500">Planlanmış zaman yok. Takvim sayfasında kartı sürükleyerek de ayırabilirsin.</p>
      )}
      {past > 0 && <p className="mt-1 text-[13px] text-slate-500">Geçmişte {past} zaman bloğu</p>}
    </div>
  )
}
