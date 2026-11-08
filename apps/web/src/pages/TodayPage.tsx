import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useBoards } from '../api/boards'
import { localDay, shiftDay, useDayPlan, useSuggestions } from '../api/dayPlans'
import DayReviewForm from '../components/DayReviewForm'
import PlanEditor from '../components/PlanEditor'
import { api } from '../lib/api'
import { formatDuration } from '../lib/format'
import type { UserSettings } from '../lib/types'

const longDate = new Intl.DateTimeFormat('tr-TR', { weekday: 'long', day: 'numeric', month: 'long' })

/** Varsayilan sekme: gecmis gun ya da degerlendirme saati gectiyse "Değerlendir". */
function defaultMode(day: string, today: string, reviewTime: string | null, reviewed: boolean) {
  if (reviewed || day < today) return 'review'
  if (day > today) return 'plan'
  if (!reviewTime) return new Date().getHours() >= 18 ? 'review' : 'plan'
  const [h, m] = reviewTime.split(':').map(Number)
  const now = new Date()
  return now.getHours() * 60 + now.getMinutes() >= h * 60 + m ? 'review' : 'plan'
}

export default function TodayPage() {
  const [params, setParams] = useSearchParams()
  const today = localDay()
  const day = params.get('date') ?? today
  const plan = useDayPlan(day)
  const suggestions = useSuggestions(day)
  const boards = useBoards()
  const settings = useQuery({ queryKey: ['settings'], queryFn: () => api<UserSettings>('/settings/') })
  const boardMap = useMemo(() => new Map((boards.data ?? []).map((b) => [b.id, b])), [boards.data])

  const mode =
    (params.get('mode') as 'plan' | 'review' | null) ??
    defaultMode(day, today, settings.data?.review_time ?? null, plan.data?.status === 'reviewed')

  const go = (next: Record<string, string>) => {
    const p: Record<string, string> = {}
    const d = next.date ?? day
    if (d !== today) p.date = d
    if (next.mode) p.mode = next.mode
    setParams(p)
  }

  const [y, mo, d] = day.split('-').map(Number)
  const label = longDate.format(new Date(y, mo - 1, d))

  return (
    <div className="mx-auto w-full max-w-5xl p-4 sm:p-6">
      <header className="mb-4 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1">
          <button onClick={() => go({ date: shiftDay(day, -1) })} className="rounded px-2 py-1 hover:bg-slate-200" aria-label="Önceki gün">‹</button>
          <button onClick={() => go({ date: shiftDay(day, 1) })} className="rounded px-2 py-1 hover:bg-slate-200" aria-label="Sonraki gün">›</button>
        </div>
        <h1 className="text-xl font-semibold">
          {day === today ? 'Bugün' : day === shiftDay(today, 1) ? 'Yarın' : day === shiftDay(today, -1) ? 'Dün' : ''}{' '}
          <span className="font-normal text-slate-500">{label}</span>
        </h1>
        {day !== today && (
          <button onClick={() => go({ date: today })} className="text-sm text-blue-600 hover:underline">bugüne dön</button>
        )}
        {plan.data && plan.data.tracked_today_sec > 0 && (
          <span className="text-sm text-slate-500">⏲ {formatDuration(plan.data.tracked_today_sec)} çalışıldı</span>
        )}
        {plan.data?.status === 'reviewed' && <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs text-green-700">Değerlendirildi ✓</span>}

        <div className="ml-auto flex rounded-md bg-slate-200 p-0.5 text-sm">
          {(['plan', 'review'] as const).map((m) => (
            <button
              key={m}
              onClick={() => go({ mode: m })}
              disabled={m === 'plan' && plan.data?.status === 'reviewed'}
              title={m === 'plan' && plan.data?.status === 'reviewed' ? 'Değerlendirilmiş günün planı değiştirilemez' : undefined}
              className={`rounded px-3 py-1 disabled:opacity-40 ${mode === m ? 'bg-white shadow-sm' : 'text-slate-600'}`}
            >
              {m === 'plan' ? 'Planla' : 'Değerlendir'}
            </button>
          ))}
        </div>
      </header>

      {(plan.isLoading || suggestions.isLoading) && <p className="text-slate-500">Yükleniyor…</p>}
      {(plan.error || suggestions.error) && <p className="text-red-600">{(plan.error ?? suggestions.error)?.message}</p>}

      {plan.data && suggestions.data && (
        mode === 'plan' && plan.data.status !== 'reviewed' ? (
          <PlanEditor day={day} plan={plan.data} suggestions={suggestions.data} boards={boardMap} />
        ) : (
          <DayReviewForm day={day} plan={plan.data} suggestions={suggestions.data} boards={boardMap} />
        )
      )}
    </div>
  )
}
