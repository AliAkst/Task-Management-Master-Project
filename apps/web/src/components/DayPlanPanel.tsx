import { Link } from 'react-router-dom'
import { useDayPlan, useDayPlanMutations, localDay, shiftDay } from '../api/dayPlans'
import type { BoardWithCounts } from '../lib/types'

const MAX_ITEMS = 12

function dayLabel(day: string): string {
  const today = localDay()
  if (day === today) return 'Bugün'
  if (day === shiftDay(today, 1)) return 'Yarın'
  if (day === shiftDay(today, -1)) return 'Dün'
  const [y, m, d] = day.split('-').map(Number)
  return new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short', weekday: 'short' }).format(
    new Date(y, m - 1, d),
  )
}

const hhmm = (iso: string) =>
  new Date(iso).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit', hour12: false })

/** Takvim sol panelinde secili gunun plani (salt gorunum + tamamla). Duzenleme Bugun'de. */
export default function DayPlanPanel({
  day,
  boards,
}: {
  day: string
  boards: Map<number, BoardWithCounts>
}) {
  const plan = useDayPlan(day)
  const m = useDayPlanMutations(day)
  const href = day === localDay() ? '/today' : `/today?date=${day}`
  const items = (plan.data?.items ?? []).filter((i) => i.was_planned)
  const shown = items.slice(0, MAX_ITEMS)

  return (
    <section>
      <div className="mb-2 flex items-baseline gap-2">
        <h2 className="text-[17px]">Günün planı</h2>
        <span className="text-[13px] text-slate-500">{dayLabel(day)}</span>
        <Link to={href} className="ml-auto text-[13px] text-blue-600 hover:underline">
          Düzenle
        </Link>
      </div>
      {plan.data?.status === 'reviewed' && (
        <p className="mb-1 text-[12px] text-slate-500">Değerlendirildi</p>
      )}
      {plan.isLoading && <p className="text-[14px] text-slate-500">Yükleniyor…</p>}
      {plan.isError && <p className="text-[14px] text-red-700">{plan.error.message}</p>}
      {m.patchItem.isError && <p className="text-[14px] text-red-700">{m.patchItem.error.message}</p>}
      {plan.data && items.length === 0 && (
        <p className="text-[14px] text-slate-500">
          Bu gün için plan yok. Bir kartı takvime sürükle ya da Bugün&apos;de ekle.
        </p>
      )}
      {shown.length > 0 && (
        <ul className="divide-y divide-slate-200">
          {shown.map((i) => {
            const done = i.outcome === 'done' || i.card_status === 'completed'
            const color = (i.board_id != null ? boards.get(i.board_id)?.color : undefined) ?? 'var(--color-slate-300)'
            return (
              <li key={i.id} className="flex items-center gap-2 py-1.5 text-[14px]">
                <input
                  type="checkbox"
                  checked={done}
                  disabled={m.patchItem.isPending}
                  aria-label={`${i.title} tamamlandı`}
                  onChange={(e) => m.patchItem.mutate({ id: i.id, body: { done: e.target.checked } })}
                />
                <span className="h-4 w-1 shrink-0 rounded-full" style={{ backgroundColor: color }} aria-hidden />
                <span className={`min-w-0 flex-1 leading-snug ${done ? 'text-slate-500 line-through' : 'text-slate-900'}`}>
                  {i.title}
                </span>
                {i.planned_start && (
                  <span className="shrink-0 text-[12px] tabular-nums text-slate-500">{hhmm(i.planned_start)}</span>
                )}
              </li>
            )
          })}
        </ul>
      )}
      {items.length > MAX_ITEMS && (
        <Link to={href} className="mt-1 inline-block text-[13px] text-blue-600 hover:underline">
          +{items.length - MAX_ITEMS} madde daha
        </Link>
      )}
    </section>
  )
}
