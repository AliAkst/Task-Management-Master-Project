import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Square, Timer } from 'lucide-react'
import { useActiveSession, useElapsed, useSessionMutations } from '../api/sessions'
import { formatClock } from '../lib/format'

const BASE_TITLE = 'Yaşam Planlayıcı'
const LONG_RUN_SEC = 8 * 3600

/** Sol raydaki global kronometre: her sayfada calisan oturumu gosterir. */
export default function TimerWidget() {
  const active = useActiveSession()
  const m = useSessionMutations()
  const s = active.data ?? null
  const elapsed = useElapsed(s?.started_at)
  const label = s ? (s.card_title ?? 'Serbest çalışma') : null

  // Sekme basliginda da sure gorunsun
  useEffect(() => {
    document.title = s ? `▶ ${formatClock(elapsed)} · ${label}` : BASE_TITLE
  }, [s, elapsed, label])
  useEffect(() => () => void (document.title = BASE_TITLE), [])

  if (!s) {
    return (
      <button
        onClick={() => m.start.mutate(null)}
        disabled={m.start.isPending}
        title="Karta bağlı olmayan çalışma süresi başlat"
        className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-[15px] text-slate-700 hover:bg-slate-100"
      >
        <Timer size={17} strokeWidth={1.75} aria-hidden />
        Serbest çalışma başlat
      </button>
    )
  }

  const longRun = elapsed > LONG_RUN_SEC
  const cardLink = s.card_id && s.board_id ? `/boards/${s.board_id}?card=${s.card_id}` : null

  return (
    <div
      className={`rounded-lg border bg-white px-2.5 py-2 ${longRun ? 'border-amber-400' : 'border-[var(--color-rec)]/40'}`}
      title={longRun ? '8 saatten uzun süredir çalışıyor — durdurmayı unutmuş olabilir misin?' : undefined}
    >
      <div className="flex items-center gap-2">
        <span className="h-2 w-2 shrink-0 animate-pulse rounded-full bg-[var(--color-rec)]" aria-hidden />
        <span className="text-[22px] leading-none font-[650] tabular-nums" style={{ fontFamily: 'var(--font-display)' }}>
          {formatClock(elapsed)}
        </span>
        <button
          onClick={() => m.stop.mutate()}
          disabled={m.stop.isPending}
          aria-label="Kronometreyi durdur"
          title="Durdur"
          className="ml-auto rounded-md bg-slate-900 p-1.5 text-white hover:bg-slate-700 disabled:opacity-50"
        >
          <Square size={12} fill="currentColor" aria-hidden />
        </button>
      </div>
      {cardLink ? (
        <Link to={cardLink} className="mt-1 block truncate text-[13px] text-slate-600 hover:text-slate-900 hover:underline">
          {label}
        </Link>
      ) : (
        <p className="mt-1 truncate text-[13px] text-slate-600">{label}</p>
      )}
      {longRun && <p className="mt-1 text-[12px] text-amber-800">8 saati geçti — unutulmuş olabilir mi?</p>}
    </div>
  )
}
