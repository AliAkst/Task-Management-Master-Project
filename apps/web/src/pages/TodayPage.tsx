import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { CheckCircle2, ChevronLeft, ChevronRight, Timer } from 'lucide-react'
import { useBoards } from '../api/boards'
import { localDay, shiftDay, useDayPlan, useSuggestions } from '../api/dayPlans'
import { useStartDayReview } from '../api/assistant'
import { PlanProposal, ReviewDigest } from '../components/DayDigest'
import DayReviewForm from '../components/DayReviewForm'
import PlanEditor from '../components/PlanEditor'
import { Segmented } from '../components/Page'
import { api } from '../lib/api'
import { formatDuration } from '../lib/format'
import type { UserSettings } from '../lib/types'

const dayMonth = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'long' })
const weekday = new Intl.DateTimeFormat('tr-TR', { weekday: 'long' })

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
  const startReview = useStartDayReview()
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
  const date = new Date(y, mo - 1, d)
  const relative = day === today ? 'Bugün' : day === shiftDay(today, 1) ? 'Yarın' : day === shiftDay(today, -1) ? 'Dün' : null

  return (
    <div className="mx-auto w-full max-w-6xl p-4 sm:p-6">
      {/* Ajanda sayfasi basligi: gun, sayfanin en buyuk ogesi */}
      <header className="mb-8 flex flex-wrap items-end gap-x-6 gap-y-3 border-b border-slate-200 pb-4">
        <div>
          <p className="flex items-center gap-1 text-[15px] text-slate-600">
            <button onClick={() => go({ date: shiftDay(day, -1) })} className="rounded p-1 hover:bg-slate-200" aria-label="Önceki gün">
              <ChevronLeft size={16} aria-hidden />
            </button>
            <span className="min-w-14 text-center">{relative ?? weekday.format(date)}</span>
            <button onClick={() => go({ date: shiftDay(day, 1) })} className="rounded p-1 hover:bg-slate-200" aria-label="Sonraki gün">
              <ChevronRight size={16} aria-hidden />
            </button>
            {day !== today && (
              <button onClick={() => go({ date: today })} className="ml-2 text-blue-600 hover:underline">Bugüne dön</button>
            )}
          </p>
          <h1 className="text-[44px] leading-[1.05]">
            {dayMonth.format(date)}
            <span className="ml-3 text-[22px] font-[500] text-slate-500">{weekday.format(date)}</span>
          </h1>
        </div>
        <div className="flex flex-wrap items-center gap-4 pb-1.5 text-[14px] text-slate-600">
          {plan.data && plan.data.tracked_today_sec > 0 && (
            <span className="inline-flex items-center gap-1.5"><Timer size={15} strokeWidth={1.75} aria-hidden />{formatDuration(plan.data.tracked_today_sec)} çalışıldı</span>
          )}
          {plan.data?.status === 'reviewed' && (
            <span className="inline-flex items-center gap-1.5 text-green-700"><CheckCircle2 size={15} strokeWidth={1.75} aria-hidden />Değerlendirildi</span>
          )}
        </div>

        <div className="ml-auto pb-1">
          <Segmented
            label="Mod"
            value={mode}
            onChange={(m) => go({ mode: m })}
            options={[
              {
                value: 'plan' as const,
                label: 'Planla',
                disabled: plan.data?.status === 'reviewed',
                title: plan.data?.status === 'reviewed' ? 'Değerlendirilmiş günün planı değiştirilemez' : undefined,
              },
              { value: 'review' as const, label: 'Değerlendir' },
            ]}
          />
        </div>
      </header>

      {(plan.isLoading || suggestions.isLoading) && <p className="text-slate-500">Yükleniyor…</p>}
      {(plan.error || suggestions.error) && <p className="text-red-600">{(plan.error ?? suggestions.error)?.message}</p>}

      {plan.data && suggestions.data && (
        mode === 'plan' && plan.data.status !== 'reviewed' ? (
          <>
            <PlanProposal day={day} />
            <PlanEditor day={day} plan={plan.data} suggestions={suggestions.data} boards={boardMap} />
          </>
        ) : (
          <>
            <ReviewDigest
              day={day}
              aiSummary={plan.data.ai_summary}
              reviewed={plan.data.status === 'reviewed'}
              onStart={() => startReview.mutate(day)}
              starting={startReview.isPending}
              startError={startReview.error?.message ?? null}
            />
            <DayReviewForm
              day={day}
              plan={plan.data}
              suggestions={suggestions.data}
              boards={boardMap}
              onReviewed={() => startReview.mutate(day)}
            />
          </>
        )
      )}
    </div>
  )
}
