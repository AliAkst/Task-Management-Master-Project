import { useEffect, useRef } from 'react'
import { LoaderCircle, Sparkles } from 'lucide-react'
import { useBoards } from '../api/boards'
import { useInboxTriageJob, useStartInboxTriage } from '../api/assistant'
import ActionCard from './ActionCard'

const DAY_KEY = 'ajanda.inboxTriageDay'

function today() {
  return new Date().toLocaleDateString('sv-SE') // YYYY-MM-DD (yerel gun)
}

/**
 * Uygulama acilisinda, Gelen Kutusu'nda kart varsa asistan dagitim onerisini
 * hazirlar (gunde en fazla bir kez). Hata sessizce yutulur: Gelen Kutusu sayfasindaki
 * "Asistan dagitsin" dugmesi hep kullanilabilir.
 */
export function useAutoInboxTriage() {
  const boards = useBoards()
  const start = useStartInboxTriage()
  const done = useRef(false)
  const inbox = boards.data?.find((b) => b.system_kind === 'inbox')
  const waiting = inbox?.open_card_count ?? 0

  useEffect(() => {
    if (done.current || waiting === 0) return
    done.current = true
    try {
      if (localStorage.getItem(DAY_KEY) === today()) return
      localStorage.setItem(DAY_KEY, today())
    } catch {
      // localStorage yoksa yine de bu oturumda bir kez dene
    }
    start.mutate()
  }, [waiting, start])
}

/** Gelen Kutusu board'unun ustunde: asistanin dagitim onerisi. */
export default function InboxTriage({ openCount }: { openCount: number }) {
  const job = useInboxTriageJob()
  const start = useStartInboxTriage()
  const j = job.data
  const running = j?.status === 'queued' || j?.status === 'running'
  const retry = (
    <button
      onClick={() => start.mutate()}
      disabled={start.isPending || running}
      className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 px-3 py-1.5 text-[14px] hover:border-slate-900 disabled:opacity-50"
    >
      <Sparkles size={14} aria-hidden /> Asistan dağıtsın
    </button>
  )

  if (openCount === 0 && !running) return null
  const moves = j?.status === 'done' ? (j.result?.moves ?? []) : []
  const pending = j?.action && j.action.status === 'proposed'

  return (
    <section aria-label="Asistan dağıtımı" className="border-b border-slate-200 bg-slate-50 py-3 pr-4 pl-6">
      {running ? (
        <p className="flex items-center gap-2 text-[15px]" aria-live="polite">
          <LoaderCircle size={16} className="animate-spin text-blue-700 motion-reduce:animate-none" aria-hidden />
          {j.status === 'queued' ? 'Sırada bekliyor…' : 'Asistan kartları board\'lara dağıtıyor…'}
          <span className="text-[13px] text-slate-500">{j.model_label}</span>
        </p>
      ) : (
        <div className="space-y-2">
          {j?.status === 'failed' && <p className="text-[14px] text-red-700">Dağıtım hazırlanamadı: {j.error}</p>}
          {moves.length > 0 && j?.action && (
            <ActionCard
              key={j.action.id + j.action.status}
              action={j.action}
              items={moves.map((m) => ({
                id: m.card_id,
                title: m.title,
                detail: `${m.board} / ${m.list}`,
                reason: m.reason,
              }))}
            />
          )}
          {j?.status === 'done' && moves.length === 0 && j.result && j.result.notes.length > 0 && (
            <p className="text-[14px] text-slate-600">{j.result.notes.join(' ')}</p>
          )}
          {j?.status === 'done' && j.model_label && moves.length > 0 && pending && (
            <p className="text-[12px] text-slate-500">Öneri: {j.model_label}. Onaylamadan hiçbir kart taşınmaz.</p>
          )}
          {!pending && (
            <div className="flex flex-wrap items-center gap-3">
              {retry}
              <span className="text-[13px] text-slate-500">{openCount} kart dağıtılmayı bekliyor</span>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
