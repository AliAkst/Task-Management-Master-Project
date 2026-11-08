import {
  Repeat,
  AlignLeft,
  CalendarDays,
  Check,
  CornerDownRight,
  Hourglass,
  Link2,
  Paperclip,
  ListChecks,
  ListTree,
  StickyNote,
  Timer,
  type LucideIcon,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { describeRule } from '../lib/rrule'
import type { CardSummary, Label } from '../lib/types'
import { useActiveSession } from '../api/sessions'
import { formatDuration, formatShortDate, isOverdue, PRIORITY_LABEL } from '../lib/format'

interface Props {
  card: CardSummary
  labels: Map<number, Label>
  dragging?: boolean
}

function Meta({ icon: Icon, children, className = '', title }: { icon: LucideIcon; children?: ReactNode; className?: string; title?: string }) {
  return (
    <span className={`inline-flex items-center gap-1 ${className}`} title={title}>
      <Icon size={13} strokeWidth={1.75} aria-hidden />
      {children}
    </span>
  )
}

/** Kanban'daki kart yuzu (liste icinde ve suruklenirken ayni gorunum). */
export default function CardFace({ card, labels, dragging }: Props) {
  const done = card.status === 'completed'
  const active = useActiveSession()
  const tracking = active.data?.card_id === card.id
  const trackedSec = card.tracked_seconds + card.subtask_tracked_seconds
  const overdue = !done && isOverdue(card.due_date)
  const high = card.priority === 'high'

  return (
    <div
      className={`relative rounded-md border bg-white px-3 py-2.5 text-[14px] leading-snug ${
        dragging ? 'rotate-2 scale-[1.03] cursor-grabbing border-slate-400 shadow-[0_12px_28px_-6px_rgb(23_32_56/0.45)]' : 'border-slate-200 hover:border-slate-400'
      } ${tracking ? 'border-l-[3px] border-l-[var(--color-rec)]' : high && !done ? 'border-l-[3px] border-l-slate-900' : ''}`}
    >
      {card.label_ids.length > 0 && (
        <div className="mb-1.5 flex flex-wrap gap-1">
          {card.label_ids.map((id) => {
            const lb = labels.get(id)
            return lb ? (
              <span key={id} className="inline-flex items-center gap-1 text-[11px] text-slate-600">
                <span className="h-1.5 w-3 rounded-full" style={{ backgroundColor: lb.color }} aria-hidden />
                {lb.name}
              </span>
            ) : null
          })}
        </div>
      )}

      <p className={done ? 'text-slate-400 line-through decoration-slate-300' : card.blocked ? 'text-slate-500' : 'text-slate-900'}>
        {card.parent_id != null && <CornerDownRight size={13} className="mr-1 inline align-[-2px] text-slate-400" aria-label="Alt kart" />}
        {card.title}
      </p>

      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-slate-500">
        {high && !done && <span className="font-semibold text-slate-900">{PRIORITY_LABEL.high} öncelik</span>}
        {done && <Meta icon={Check} className="text-green-700">Tamamlandı</Meta>}
        {card.due_date && (
          <Meta icon={CalendarDays} className={overdue ? 'font-semibold text-red-700' : ''} title={overdue ? 'Son tarih geçti' : 'Son tarih'}>
            {formatShortDate(card.due_date)}
          </Meta>
        )}
        {tracking ? (
          <span className="inline-flex items-center gap-1 text-[var(--color-rec)]">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--color-rec)]" aria-hidden />
            çalışılıyor
          </span>
        ) : trackedSec > 0 ? (
          <Meta icon={Timer} title={card.estimated_minutes ? `Harcanan / tahmin` : 'Harcanan süre'}>
            {formatDuration(trackedSec)}
            {card.estimated_minutes != null && <span className="text-slate-400">/ {formatDuration(card.estimated_minutes * 60)}</span>}
          </Meta>
        ) : (
          card.estimated_minutes != null && <Meta icon={Hourglass} title="Tahmini süre">{formatDuration(card.estimated_minutes * 60)}</Meta>
        )}
        {card.checklist_total > 0 && (
          <Meta icon={ListChecks} className={card.checklist_done === card.checklist_total ? 'text-green-700' : ''} title="Checklist">
            {card.checklist_done}/{card.checklist_total}
          </Meta>
        )}
        {card.subtask_total > 0 && (
          <Meta icon={ListTree} className={card.subtask_done === card.subtask_total ? 'text-green-700' : ''} title="Alt kartlar">
            {card.subtask_done}/{card.subtask_total}
          </Meta>
        )}
        {card.blocked && (
          <Meta icon={Link2} className="text-amber-700" title={`${card.blocked_by_count} ön koşul bitmedi`}>
            Bekliyor
          </Meta>
        )}
        {card.recurrence_rule && (
          <Meta icon={Repeat} title={`Tekrarlayan iş: ${describeRule(card.recurrence_rule)}`}>
            {card.series_index != null && card.series_index > 1 ? `${card.series_index}.` : null}
          </Meta>
        )}
        {card.note_count > 0 && <Meta icon={StickyNote} title="Notlar">{card.note_count}</Meta>}
        {card.attachment_count > 0 && <Meta icon={Paperclip} title="Ekler">{card.attachment_count}</Meta>}
        {card.has_description && <Meta icon={AlignLeft} title="Açıklama var" />}
      </div>
    </div>
  )
}
