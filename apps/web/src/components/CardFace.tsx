import type { CardSummary, Label } from '../lib/types'
import { useActiveSession } from '../api/sessions'
import { formatDuration, formatShortDate, isOverdue, PRIORITY_DOT } from '../lib/format'

interface Props {
  card: CardSummary
  labels: Map<number, Label>
  dragging?: boolean
}

/** Kanban'daki kart yuzu (liste icinde ve suruklenirken ayni gorunum). */
export default function CardFace({ card, labels, dragging }: Props) {
  const done = card.status === 'completed'
  const active = useActiveSession()
  const tracking = active.data?.card_id === card.id
  const trackedSec = card.tracked_seconds + card.subtask_tracked_seconds
  const overdue = !done && isOverdue(card.due_date)
  return (
    <div
      className={`rounded-lg bg-white p-2.5 text-sm shadow-sm ring-1 ring-slate-200 ${
        dragging ? 'rotate-2 shadow-lg' : 'hover:ring-slate-400'
      }`}
    >
      {card.label_ids.length > 0 && (
        <div className="mb-1.5 flex flex-wrap gap-1">
          {card.label_ids.map((id) => {
            const lb = labels.get(id)
            return lb ? (
              <span
                key={id}
                className="rounded px-1.5 py-0.5 text-[10px] font-medium text-white"
                style={{ backgroundColor: lb.color }}
              >
                {lb.name}
              </span>
            ) : null
          })}
        </div>
      )}
      <div className="flex items-start gap-1.5">
        <span
          className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${PRIORITY_DOT[card.priority]}`}
          title={`Öncelik: ${card.priority}`}
        />
        <span className={done ? 'text-slate-400 line-through' : card.blocked ? 'text-slate-500' : ''}>
          {card.parent_id != null && <span className="mr-1 text-slate-400">↳</span>}
          {card.title}
        </span>
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
        {done && <span className="text-green-600">✓ Tamamlandı</span>}
        {card.due_date && (
          <span className={overdue ? 'font-medium text-red-600' : ''}>📅 {formatShortDate(card.due_date)}</span>
        )}
        {card.estimated_minutes != null && <span>⏱ {card.estimated_minutes} dk</span>}
        {card.checklist_total > 0 && (
          <span className={card.checklist_done === card.checklist_total ? 'text-green-600' : ''}>
            ☑ {card.checklist_done}/{card.checklist_total}
          </span>
        )}
        {card.note_count > 0 && <span>📝 {card.note_count}</span>}
        {tracking ? (
          <span className="flex items-center gap-1 text-red-600">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-red-500" /> çalışılıyor
          </span>
        ) : (
          trackedSec > 0 && <span title="Harcanan süre">⏲ {formatDuration(trackedSec)}</span>
        )}
        {card.subtask_total > 0 && (
          <span className={card.subtask_done === card.subtask_total ? 'text-green-600' : ''}>
            ↳ {card.subtask_done}/{card.subtask_total}
          </span>
        )}
        {card.blocked && (
          <span className="text-amber-600" title={`${card.blocked_by_count} ön koşul bitmedi`}>
            ⛓ Bekliyor
          </span>
        )}
        {card.has_description && <span title="Açıklama var">≡</span>}
      </div>
    </div>
  )
}
