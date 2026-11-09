import { PencilLine, Timer } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useActiveSession, useCardSessions, useElapsed, useSessionMutations } from '../api/sessions'
import { formatClock, formatDuration, formatRange, fromLocalInput, toLocalInput } from '../lib/format'
import type { CardDetail } from '../lib/types'

/** Kart detayi basligindaki kronometre dugmesi. */
export function CardTimerButton({ cardId }: { cardId: number }) {
  const active = useActiveSession()
  const m = useSessionMutations()
  const running = active.data?.card_id === cardId
  const elapsed = useElapsed(running ? active.data?.started_at : null)

  if (running) {
    return (
      <button
        onClick={() => m.stop.mutate()}
        disabled={m.stop.isPending}
        className="flex items-center gap-1.5 rounded-full bg-red-50 px-3 py-1 text-sm text-red-700 hover:bg-red-100"
      >
        <span className="h-2 w-2 animate-pulse rounded-full bg-red-500" />
        <span className="font-mono tabular-nums">{formatClock(elapsed)}</span> ■
      </button>
    )
  }
  return (
    <button
      onClick={() => m.start.mutate(cardId)}
      disabled={m.start.isPending}
      title={active.data ? 'Çalışan kronometre durdurulup bu kart için başlatılır' : undefined}
      className="rounded-full bg-slate-900 px-3 py-1 text-sm text-on-ink hover:bg-slate-700 disabled:opacity-50"
    >
      ▶ Başla
    </button>
  )
}

/** Kart detayindaki "Harcanan süre" bolumu. */
export default function CardTime({ card }: { card: CardDetail }) {
  const active = useActiveSession()
  const sessions = useCardSessions(card.id)
  const m = useSessionMutations()
  const running = active.data?.card_id === card.id
  const live = useElapsed(running ? active.data?.started_at : null)

  const [adding, setAdding] = useState(false)
  const [start, setStart] = useState(() => toLocalInput(new Date(Date.now() - 3600_000)))
  const [minutes, setMinutes] = useState('60')

  const own = card.tracked_seconds + (running ? live : 0)
  const total = own + card.subtask_tracked_seconds
  const estimateSec = (card.estimated_minutes ?? 0) * 60
  const ratio = estimateSec > 0 ? total / estimateSec : 0

  function submit(e: FormEvent) {
    e.preventDefault()
    const s = new Date(fromLocalInput(start))
    const end = new Date(s.getTime() + Math.max(1, Number(minutes) || 0) * 60_000)
    m.createManual.mutate(
      { card_id: card.id, started_at: s.toISOString(), ended_at: end.toISOString() },
      { onSuccess: () => setAdding(false) },
    )
  }

  const finished = (sessions.data ?? []).filter((s) => !s.is_running)

  return (
    <div className="mt-7">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-[15px] font-semibold text-slate-900">Harcanan süre</h3>
        <button onClick={() => setAdding((a) => !a)} aria-expanded={adding} className="shrink-0 text-[13px] text-blue-700 hover:underline">
          Elle ekle
        </button>
      </div>
      <p className="mb-2 text-[14px] text-slate-700 tabular-nums">
        {formatDuration(total)}
        {estimateSec > 0 && <span className="text-slate-500"> / {formatDuration(estimateSec)} tahmin</span>}
        {card.subtask_tracked_seconds > 0 && (
          <span className="block text-[13px] text-slate-500">Alt kartlarda: {formatDuration(card.subtask_tracked_seconds)}</span>
        )}
      </p>

      {estimateSec > 0 && (
        <div className="mb-2 h-1.5 rounded-full bg-slate-200" title={`Tahminin %${Math.round(ratio * 100)}'i`}>
          <div
            className={`h-1.5 rounded-full ${ratio > 1 ? 'bg-amber-600' : 'bg-blue-600'}`}
            style={{ width: `${Math.min(100, ratio * 100)}%` }}
          />
        </div>
      )}

      {adding && (
        <form onSubmit={submit} className="mb-2 flex flex-wrap items-end gap-2 rounded-md bg-slate-50 p-2 text-sm">
          <input type="datetime-local" required className="rounded border border-slate-300 px-2 py-1" value={start} onChange={(e) => setStart(e.target.value)} />
          <label className="flex items-center gap-1">
            <input type="number" min={1} className="w-20 rounded border border-slate-300 px-2 py-1" value={minutes} onChange={(e) => setMinutes(e.target.value)} />
            dk
          </label>
          <button disabled={m.createManual.isPending} className="rounded-md bg-slate-900 px-3 py-1 text-on-ink disabled:opacity-50">Ekle</button>
          {m.createManual.error && <span className="text-red-600">{m.createManual.error.message}</span>}
        </form>
      )}

      <ul className="space-y-1 text-sm">
        {finished.slice(0, 5).map((s) => (
          <li key={s.id} className="group flex items-center gap-2">
            <span className="text-slate-400" title={s.source === 'manual' ? 'Elle girildi' : 'Kronometre'}>
              {s.source === 'manual' ? <PencilLine size={13} aria-label="Elle girildi" /> : <Timer size={13} aria-label="Kronometre" />}
            </span>
            <span className="flex-1">{formatRange(s.started_at, s.ended_at!, false)}</span>
            <span className="text-xs text-slate-500">{formatDuration(s.duration_sec ?? 0)}</span>
            <button
              onClick={() => confirm('Bu çalışma kaydı silinsin mi?') && m.remove.mutate(s.id)}
              className="text-xs text-slate-400 opacity-0 group-hover:opacity-100 hover:text-red-600"
            >
              Sil
            </button>
          </li>
        ))}
      </ul>
      {finished.length > 5 && <p className="mt-1 text-[13px] text-slate-500">ve {finished.length - 5} kayıt daha</p>}
      {finished.length === 0 && !running && !adding && (
        <p className="text-[13px] text-slate-500">Henüz süre kaydı yok. Üstteki “Başla” ile kronometreyi çalıştır.</p>
      )}
    </div>
  )
}
