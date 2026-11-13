import { CalendarClock, X } from 'lucide-react'
import type { WhenMatch } from '../lib/types'

/** Baslikta algilanan zaman ifadesinin onizleme rozeti (kabul = Enter, red = ×). */
export default function WhenBadge({
  match,
  onDismiss,
  schedule,
}: {
  match: WhenMatch
  onDismiss: () => void
  schedule?: { checked: boolean; onChange: (v: boolean) => void }
}) {
  return (
    <div role="status" aria-live="polite" className="flex flex-wrap items-center gap-2 text-xs">
      <span className="inline-flex items-center gap-1.5 rounded-md bg-slate-100 px-2 py-0.5 text-slate-700 ring-1 ring-slate-300">
        <CalendarClock size={14} aria-hidden />
        <span className="sr-only">Son tarih algılandı: </span>
        {match.label.replace(/^📅\s*/, '')}
        <button
          type="button"
          aria-label="Algılanan tarihi kullanma"
          title="Algılanan tarihi kullanma"
          className="-mr-1 rounded p-0.5 text-slate-500 hover:bg-slate-200 hover:text-slate-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-slate-500"
          onClick={onDismiss}
        >
          <X size={12} />
        </button>
      </span>
      {schedule && match.has_time && match.estimated_minutes ? (
        <label className="inline-flex items-center gap-1 text-slate-600">
          <input
            type="checkbox"
            className="h-3.5 w-3.5 accent-slate-700"
            checked={schedule.checked}
            onChange={(e) => schedule.onChange(e.target.checked)}
          />
          Takvime de koy
        </label>
      ) : null}
    </div>
  )
}
