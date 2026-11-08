import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useActiveSession, useElapsed, useSessionMutations } from '../api/sessions'
import { formatClock } from '../lib/format'

const BASE_TITLE = 'Yaşam Planlayıcı'
const LONG_RUN_SEC = 8 * 3600

/** Ust menudeki global kronometre: her sayfada calisan oturumu gosterir. */
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
        className="rounded-md px-2.5 py-1 text-sm whitespace-nowrap text-slate-500 hover:bg-slate-100"
      >
        ▶ Serbest
      </button>
    )
  }

  const longRun = elapsed > LONG_RUN_SEC
  const cardLink = s.card_id && s.board_id ? `/boards/${s.board_id}?card=${s.card_id}` : null

  return (
    <div
      className={`flex items-center gap-2 rounded-full py-1 pr-1 pl-3 text-sm ${
        longRun ? 'bg-amber-100' : 'bg-red-50'
      }`}
      title={longRun ? '8 saatten uzun süredir çalışıyor — durdurmayı unutmuş olabilir misin?' : undefined}
    >
      <span className="h-2 w-2 animate-pulse rounded-full bg-red-500" />
      {cardLink ? (
        <Link to={cardLink} className="max-w-24 truncate hover:underline lg:max-w-56">{label}</Link>
      ) : (
        <span className="max-w-24 truncate lg:max-w-56">{label}</span>
      )}
      <span className="font-mono tabular-nums">{formatClock(elapsed)}</span>
      <button
        onClick={() => m.stop.mutate()}
        disabled={m.stop.isPending}
        className="rounded-full bg-slate-900 px-2.5 py-0.5 text-xs text-white disabled:opacity-50"
      >
        ■ Durdur
      </button>
    </div>
  )
}
