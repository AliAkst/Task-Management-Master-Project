import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeftRight, Play, Square } from 'lucide-react'
import { useActiveSession, useElapsed, useSessionMutations } from '../api/sessions'
import { formatClock } from '../lib/format'
import { useFocusPrefs } from '../stores/focus'
import FocusPicker from './FocusPicker'

const BASE_TITLE = 'Yaşam Planlayıcı'
const LONG_RUN_SEC = 8 * 3600

function notifyFocusDone(key: string, label: string, minutes: number) {
  try {
    if (sessionStorage.getItem(key)) return
    sessionStorage.setItem(key, '1')
  } catch {
    /* depolama yok: yine de bir kez dene */
  }
  try {
    if ('Notification' in window && Notification.permission === 'granted') {
      new Notification(`${minutes} dakika doldu`, { body: `${label}: kısa bir mola ver.`, tag: key })
    }
  } catch {
    /* bildirim desteklenmiyor */
  }
}

/**
 * Sol raydaki kronometre. Bostayken "Çalışmaya başla" kart secicisini acar
 * (bugunun plani + acik kartlar); calisirken sure, kart ve istege bagli odak
 * suresi (pomodoro) geri sayimi gorunur. Kayit odak suresi dolunca durmaz.
 */
export default function TimerWidget() {
  const active = useActiveSession()
  const m = useSessionMutations()
  const focusMinutes = useFocusPrefs((s) => s.focusMinutes)
  const [picking, setPicking] = useState(false)
  const s = active.data ?? null
  const elapsed = useElapsed(s?.started_at)
  const label = s ? (s.card_title ?? 'Serbest çalışma') : null
  const focusSec = focusMinutes ? focusMinutes * 60 : null
  const remaining = focusSec != null ? focusSec - elapsed : null
  const focusDone = remaining != null && remaining <= 0

  // Sekme basliginda da sure gorunsun
  useEffect(() => {
    document.title = s
      ? `${focusDone ? 'Mola' : '▶'} ${formatClock(remaining != null && !focusDone ? remaining : elapsed)} · ${label}`
      : BASE_TITLE
  }, [s, elapsed, label, remaining, focusDone])
  useEffect(() => () => void (document.title = BASE_TITLE), [])
  useEffect(() => {
    if (s && focusDone && focusMinutes) notifyFocusDone(`focus:${s.id}:${focusMinutes}`, label ?? '', focusMinutes)
  }, [s, focusDone, focusMinutes, label])

  const picker = picking && <FocusPicker onClose={() => setPicking(false)} currentCardId={s?.card_id ?? null} />

  if (!s) {
    return (
      <div className="relative">
        <button
          onClick={() => setPicking((v) => !v)}
          aria-expanded={picking}
          className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-[15px] text-slate-700 hover:bg-slate-100"
        >
          <Play size={17} strokeWidth={1.75} aria-hidden />
          Çalışmaya başla
        </button>
        {picker}
      </div>
    )
  }

  const longRun = elapsed > LONG_RUN_SEC
  const cardLink = s.card_id && s.board_id ? `/boards/${s.board_id}?card=${s.card_id}` : null

  return (
    <div className="relative">
      <div
        className={`rounded-lg border bg-surface px-2.5 py-2 ${longRun || focusDone ? 'border-amber-400' : 'border-[var(--color-rec)]/40'}`}
        title={longRun ? '8 saatten uzun süredir çalışıyor — durdurmayı unutmuş olabilir misin?' : undefined}
      >
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 shrink-0 animate-pulse rounded-full bg-[var(--color-rec)] motion-reduce:animate-none" aria-hidden />
          <span className="text-[22px] leading-none font-[650] tabular-nums" style={{ fontFamily: 'var(--font-display)' }}>
            {formatClock(elapsed)}
          </span>
          <button
            onClick={() => setPicking((v) => !v)}
            aria-label="Başka bir karta geç"
            title="Başka bir karta geç"
            className="ml-auto rounded-md p-1.5 text-slate-600 hover:bg-slate-100"
          >
            <ArrowLeftRight size={13} aria-hidden />
          </button>
          <button
            onClick={() => m.stop.mutate()}
            disabled={m.stop.isPending}
            aria-label="Kronometreyi durdur"
            title="Durdur"
            className="rounded-md bg-slate-900 p-1.5 text-on-ink hover:bg-slate-700 disabled:opacity-50"
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
        {focusSec != null && (
          <div className="mt-1.5" aria-live="polite">
            <div className="h-1 overflow-hidden rounded-full bg-slate-200" aria-hidden>
              <div
                className={`h-full ${focusDone ? 'bg-amber-500' : 'bg-[var(--color-rec)]'}`}
                style={{ width: `${Math.min(100, (elapsed / focusSec) * 100)}%` }}
              />
            </div>
            <p className={`mt-1 text-[12px] ${focusDone ? 'text-amber-800' : 'text-slate-500'}`}>
              {focusDone
                ? `${focusMinutes} dk doldu, mola zamanı`
                : `Odak: ${formatClock(remaining!)} kaldı`}
            </p>
          </div>
        )}
        {longRun && <p className="mt-1 text-[12px] text-amber-800">8 saati geçti — unutulmuş olabilir mi?</p>}
      </div>
      {picker}
    </div>
  )
}
