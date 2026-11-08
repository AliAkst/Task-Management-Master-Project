import { useState } from 'react'
import { Check, LoaderCircle, ScanSearch, X } from 'lucide-react'
import { localDay } from '../api/dayPlans'
import { useInsightActions, useInsights, type Insight } from '../api/insights'

const dateFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'long' })

/** Bekleyen gozlem: "Dogru, hatirla" (istersen duzelterek) ya da "Yanlis" (nedeniyle). */
function PendingInsight({ insight }: { insight: Insight }) {
  const { confirm, reject } = useInsightActions()
  const [mode, setMode] = useState<'view' | 'edit' | 'reject'>('view')
  const [text, setText] = useState(insight.observation)
  const [reason, setReason] = useState('')
  const busy = confirm.isPending || reject.isPending
  const data = insight.evidence.data_text
  const error = (confirm.error ?? reject.error)?.message

  return (
    <li className="py-3">
      {mode === 'edit' ? (
        <textarea
          autoFocus
          rows={2}
          maxLength={1000}
          className="w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-[16px]"
          value={text}
          onChange={(e) => setText(e.target.value)}
          aria-label="Kaydedilecek cümle"
        />
      ) : (
        // Modelin cumlesi; verideki hali (kanit) uzerine gelince gorunur
        <p className="text-[16px]" title={data ? `Veri: ${data}` : undefined}>{insight.observation}</p>
      )}
      {mode === 'reject' ? (
        <div className="mt-2 flex flex-wrap gap-2">
          <input
            autoFocus
            className="min-w-0 flex-1 rounded-md border border-slate-300 px-2 py-1 text-[14px]"
            placeholder="Neden? (opsiyonel; asistan öğrenir)"
            maxLength={2000}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            onKeyDown={(e) => e.key === 'Escape' && setMode('view')}
          />
          <button
            disabled={busy}
            onClick={() => reject.mutate({ id: insight.id, reason: reason.trim() || null })}
            className="rounded-md bg-slate-700 px-3 py-1 text-[14px] text-white disabled:opacity-50"
          >
            Reddet
          </button>
          <button onClick={() => setMode('view')} className="text-[14px] text-slate-500">Vazgeç</button>
        </div>
      ) : (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <button
            disabled={busy || !text.trim()}
            onClick={() => confirm.mutate({ id: insight.id, content: mode === 'edit' ? text.trim() : undefined })}
            className="inline-flex items-center gap-1.5 rounded-md bg-slate-900 px-3 py-1 text-[14px] text-white hover:bg-slate-700 disabled:opacity-50"
          >
            <Check size={14} aria-hidden /> Doğru, hatırla
          </button>
          {mode === 'view' && (
            <button onClick={() => setMode('edit')} className="rounded-md px-3 py-1 text-[14px] text-slate-700 ring-1 ring-slate-300 hover:ring-slate-900">
              Düzelterek kaydet
            </button>
          )}
          <button
            disabled={busy}
            onClick={() => setMode('reject')}
            className="inline-flex items-center gap-1 rounded-md px-3 py-1 text-[14px] text-slate-600 hover:bg-slate-100"
          >
            <X size={14} aria-hidden /> Doğru değil
          </button>
        </div>
      )}
      {error && <p className="mt-1 text-[13px] text-red-700">{error}</p>}
    </li>
  )
}

export default function InsightsSection() {
  const q = useInsights()
  const { analyze } = useInsightActions()
  const job = q.data?.job
  const running = job?.status === 'queued' || job?.status === 'running'
  const pending = (q.data?.items ?? []).filter((i) => i.status === 'new')
  const decided = (q.data?.items ?? []).filter((i) => i.status !== 'new').slice(0, 8)

  return (
    <section>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-[22px]">Asistanın gözlemleri</h2>
          <p className="mt-1 max-w-prose text-[15px] text-slate-600">
            Asistan haftada bir son 4 haftana bakıp kalıplarını not eder. Doğru bulduklarını onaylarsan seni
            tanıdığı bilgilere eklenir; yanlışsa reddet, 4 hafta boyunca tekrar önermez.
          </p>
        </div>
        <button
          disabled={running || analyze.isPending}
          onClick={() => analyze.mutate(localDay())}
          className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 px-3 py-1.5 text-[14px] hover:border-slate-900 disabled:opacity-50"
        >
          <ScanSearch size={15} aria-hidden /> Son 4 haftayı analiz et
        </button>
      </div>

      <div className="mt-3 text-[14px] text-slate-600" aria-live="polite">
        {running && (
          <p className="flex items-center gap-2">
            <LoaderCircle size={15} className="animate-spin text-blue-700 motion-reduce:animate-none" aria-hidden />
            {job!.model_label} haftanı inceliyor; birkaç dakika sürebilir.
          </p>
        )}
        {job?.status === 'failed' && <p className="text-red-700">Analiz yapılamadı: {job.error}</p>}
        {analyze.error && <p className="text-red-700">{analyze.error.message}</p>}
        {job?.status === 'done' && job.result && (
          <>
            {job.result.week_summary && <p className="max-w-prose text-[16px] text-slate-900">{job.result.week_summary}</p>}
            <p className="mt-1 text-[13px] text-slate-500">
              Son analiz: {dateFmt.format(new Date(job.finished_at ?? job.created_at))}, {job.model_label}
              {job.result.notes.length > 0 && `. ${job.result.notes.join(' ')}`}
            </p>
          </>
        )}
        {!job && !q.isLoading && <p>Henüz analiz yapılmadı. İlk analiz, bir günü değerlendirdikten sonra kendiliğinden çalışır.</p>}
      </div>

      {pending.length > 0 && (
        <ul className="mt-3 divide-y divide-slate-200 border-y border-slate-200">
          {pending.map((i) => <PendingInsight key={i.id} insight={i} />)}
        </ul>
      )}

      {decided.length > 0 && (
        <details className="mt-4">
          <summary className="cursor-pointer text-[14px] text-slate-600">Önceki gözlemler ({decided.length})</summary>
          <ul className="mt-2 space-y-1.5">
            {decided.map((i) => (
              <li key={i.id} className="flex items-start gap-2 text-[14px]">
                {i.status === 'confirmed' ? (
                  <Check size={14} className="mt-0.5 shrink-0 text-green-700" aria-label="Onaylandı" />
                ) : (
                  <X size={14} className="mt-0.5 shrink-0 text-slate-400" aria-label="Reddedildi" />
                )}
                <span className={i.status === 'rejected' ? 'text-slate-500' : ''}>
                  {i.observation}
                  {i.user_feedback && <span className="text-slate-500"> (nedenin: {i.user_feedback})</span>}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}
