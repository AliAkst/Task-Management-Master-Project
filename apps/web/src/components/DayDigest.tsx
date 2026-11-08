import { useEffect, useRef, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { Gauge, LoaderCircle, RotateCcw, Sparkles } from 'lucide-react'
import { useDayReviewJob, type DayReviewJob, type DayReviewPlanItem } from '../api/assistant'
import { shiftDay } from '../api/dayPlans'
import ActionCard from './ActionCard'

const KIND: Record<string, string> = {
  event: 'takvimde',
  carry_over: 'ertelenmişti',
  next_in_chain: 'zincirde sıradaki',
  due: 'son günü',
  overdue: 'son günü geçti',
  in_progress: 'devam ediyor',
  worked: 'üzerinde çalıştın',
}
const clock = new Intl.DateTimeFormat('tr-TR', { hour: '2-digit', minute: '2-digit' })
const dayMonth = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'long' })

function longDay(day: string) {
  const [y, m, d] = day.split('-').map(Number)
  return dayMonth.format(new Date(y, m - 1, d))
}

function PlanList({ items }: { items: DayReviewPlanItem[] }) {
  return (
    <ul className="divide-y divide-slate-200 border-y border-slate-200">
      {items.map((p) => {
        const meta = [KIND[p.kind] ?? p.kind]
        if (p.planned_start) meta.push(clock.format(new Date(p.planned_start)))
        if (p.adjusted_minutes) {
          meta.push(
            p.minutes && p.adjusted_minutes !== p.minutes
              ? `${p.adjusted_minutes} dk (tahminin ${p.minutes} dk)`
              : `${p.adjusted_minutes} dk`,
          )
        }
        return (
          <li key={`${p.card_id ?? 'e'}-${p.event_id ?? ''}-${p.title}`} className="py-2.5">
            <p className="flex flex-wrap items-baseline gap-x-3">
              <span className="font-semibold">{p.title}</span>
              <span className="text-[13px] text-slate-500">{meta.join(', ')}</span>
            </p>
            {p.reason && <p className="text-[14px] text-slate-600">{p.reason}</p>}
          </li>
        )
      })}
    </ul>
  )
}

/** Bitmis isin sonucu: ozet, yarin icin oneri ve onay karti. */
function Result({ job, showSummary }: { job: DayReviewJob; showSummary: boolean }) {
  const r = job.result!
  return (
    <div className="space-y-4">
      {showSummary && r.summary && <p className="max-w-prose text-[17px] leading-relaxed">{r.summary}</p>}
      {r.tip && (
        <p className="max-w-prose text-[15px] text-slate-700">
          <span className="font-semibold">{showSummary ? 'Yarın için: ' : 'Tavsiyesi: '}</span>
          {r.tip}
        </p>
      )}
      {r.plan.length > 0 && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <h3 className="text-[17px]">{longDay(r.tomorrow)} için önerdiği plan</h3>
            {r.estimate_text && (
              <p className="inline-flex items-center gap-1.5 text-[13px] text-slate-600" title="Süreler buna göre düzeltildi">
                <Gauge size={14} aria-hidden /> {r.estimate_text}; süreler buna göre ayarlandı
              </p>
            )}
          </div>
          <PlanList items={r.plan} />
          {job.action && <ActionCard key={job.action.id + job.action.status} action={job.action} />}
          {job.action?.status === 'executed' && (
            <Link to={`/today?date=${r.tomorrow}&mode=plan`} className="inline-block text-[14px] text-blue-700 hover:underline">
              {longDay(r.tomorrow)} planını aç
            </Link>
          )}
        </div>
      )}
      {r.notes.length > 0 && (
        <ul className="space-y-0.5 text-[13px] text-slate-500">
          {r.notes.map((n) => <li key={n}>{n}</li>)}
        </ul>
      )}
    </div>
  )
}

function Shell({ meta, children }: { meta?: string; children: ReactNode }) {
  return (
    <section aria-label="Asistanın notu" className="mb-8 border-l-2 border-blue-700 pl-5">
      <h2 className="mb-2 flex flex-wrap items-baseline gap-x-3 text-[20px]">
        <span className="inline-flex items-center gap-2"><Sparkles size={17} className="text-blue-700" aria-hidden /> Asistanın notu</span>
        {meta && <span className="font-sans text-[13px] font-normal text-slate-500">{meta}</span>}
      </h2>
      {children}
    </section>
  )
}

/**
 * Degerlendirilmis gunun altinda: asistanin gun ozeti ve ertesi gun icin onerisi.
 * Is arka planda surer (buyuk local model yavas olabilir); sayfa 5 sn'de bir yoklar.
 */
export function ReviewDigest({
  day,
  aiSummary,
  reviewed,
  onStart,
  starting,
  startError,
}: {
  day: string
  aiSummary: string | null | undefined
  reviewed: boolean
  onStart: () => void
  starting: boolean
  startError: string | null
}) {
  const job = useDayReviewJob(day, reviewed)
  const qc = useQueryClient()
  const prev = useRef(job.data?.status)
  useEffect(() => {
    // Is bitince: gunun ozeti (ai_summary) ve otomatik eklendiyse yarinin plani tazelensin
    if (prev.current && prev.current !== job.data?.status && job.data?.status === 'done') {
      qc.invalidateQueries({ queryKey: ['day'] })
    }
    prev.current = job.data?.status
  }, [job.data?.status, qc])

  if (!reviewed) return null
  const j = job.data
  const retry = (
    <button
      onClick={onStart}
      disabled={starting}
      className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 px-3 py-1.5 text-[14px] hover:border-slate-900 disabled:opacity-50"
    >
      <RotateCcw size={14} aria-hidden /> {j ? 'Yeniden oluştur' : 'Özetle ve yarını planla'}
    </button>
  )

  if (j && (j.status === 'queued' || j.status === 'running')) {
    const since = new Date(j.started_at ?? j.created_at).getTime()
    const minutes = Math.max(0, Math.floor((Date.now() - since) / 60000))
    return (
      <Shell meta={j.model_label}>
        <p className="flex items-center gap-2 text-[16px]" aria-live="polite">
          <LoaderCircle size={16} className="animate-spin text-blue-700 motion-reduce:animate-none" aria-hidden />
          {j.status === 'queued' ? 'Sırada bekliyor…' : 'Günü özetliyor ve yarını planlıyor…'}
          {minutes > 0 && <span className="text-[14px] text-slate-500">{minutes} dk</span>}
        </p>
        <p className="mt-1 max-w-prose text-[14px] text-slate-600">
          {j.is_local
            ? 'Bu iş büyük bir local modelle yapılıyor ve birkaç dakika sürebilir. Sayfadan çıkabilirsin; hazır olunca burada görünür.'
            : 'Bu iş bulut modelle yapılıyor; sağlayıcı hesabından ücretlendirilebilir.'}
        </p>
      </Shell>
    )
  }

  if (j?.status === 'failed') {
    return (
      <Shell meta={j.model_label}>
        <p className="text-[15px] text-red-700">Özet hazırlanamadı: {j.error}</p>
        <div className="mt-2">{retry}</div>
        {startError && <p className="mt-1 text-[13px] text-red-700">{startError}</p>}
      </Shell>
    )
  }

  if (j?.status === 'done' && j.result) {
    const at = j.finished_at ? clock.format(new Date(j.finished_at)) : null
    return (
      <Shell meta={[j.model_label, at].filter(Boolean).join(', ')}>
        {!j.result.summary && aiSummary && <p className="max-w-prose text-[17px] leading-relaxed">{aiSummary}</p>}
        <Result job={j} showSummary />
        <div className="mt-3">{retry}</div>
      </Shell>
    )
  }

  // Is yok: eski bir ozet olabilir; yoksa elle baslatma
  return (
    <Shell>
      {aiSummary ? (
        <p className="max-w-prose text-[17px] leading-relaxed">{aiSummary}</p>
      ) : (
        <p className="text-[15px] text-slate-600">Asistan bu günü henüz özetlemedi.</p>
      )}
      <div className="mt-2">{retry}</div>
      {startError && <p className="mt-1 text-[13px] text-red-700">{startError}</p>}
    </Shell>
  )
}

/** Planlama modunda: onceki aksam asistanin bu gun icin onerdigi plan (varsa). */
export function PlanProposal({ day }: { day: string }) {
  const job = useDayReviewJob(shiftDay(day, -1))
  const j = job.data
  if (!j || j.status !== 'done' || !j.result || j.result.plan.length === 0) return null
  if (j.action && j.action.status !== 'proposed') return null // karar verildi: plan zaten ortada
  return (
    <Shell meta={`${longDay(j.date)} akşamı, ${j.model_label}`}>
      <Result job={j} showSummary={false} />
    </Shell>
  )
}
