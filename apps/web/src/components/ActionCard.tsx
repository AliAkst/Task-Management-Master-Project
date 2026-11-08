import { useState } from 'react'
import { useActionDecision, type AiAction } from '../api/assistant'

const STATUS: Record<AiAction['status'], { label: string; cls: string }> = {
  proposed: { label: 'Onay bekliyor', cls: 'bg-amber-100 text-amber-800' },
  executed: { label: '✅ Yapıldı', cls: 'bg-green-100 text-green-800' },
  rejected: { label: '✗ Reddedildi', cls: 'bg-slate-200 text-slate-600' },
  failed: { label: '⚠️ Başarısız', cls: 'bg-red-100 text-red-700' },
}

/**
 * AI'in yazma islemi. "Onay bekliyor" ise islem YAPILMAMISTIR; kullanici onaylarsa
 * yapilir. "Bu tür işlemleri otomatik yap" secilirse izin ayari 'auto' olur.
 */
export default function ActionCard({ action }: { action: AiAction }) {
  const { approve, reject } = useActionDecision()
  const [current, setCurrent] = useState(action)
  const [remember, setRemember] = useState(false)
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const busy = approve.isPending || reject.isPending
  const error = (approve.error ?? reject.error)?.message
  const status = STATUS[current.status]
  const failure = current.status === 'failed' ? String(current.result?.error ?? '') : null

  return (
    <div className={`rounded-xl border bg-white p-2.5 text-sm ${current.status === 'proposed' ? 'border-amber-300' : 'border-slate-200'}`}>
      <div className="flex items-start gap-2">
        <span className="flex-1 whitespace-pre-line">{current.summary}</span>
        <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] ${status.cls}`}>{status.label}</span>
      </div>
      {failure && <p className="mt-1 text-xs text-red-700">{failure}</p>}
      {current.status === 'rejected' && current.user_feedback && (
        <p className="mt-1 text-xs text-slate-500">Nedenin: {current.user_feedback}</p>
      )}

      {current.status === 'proposed' && (
        <div className="mt-2 space-y-2">
          {rejecting ? (
            <div className="flex gap-2">
              <input
                autoFocus
                className="min-w-0 flex-1 rounded border border-slate-300 px-2 py-1 text-xs"
                placeholder="Neden? (opsiyonel — asistan öğrenir)"
                maxLength={2000}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                onKeyDown={(e) => e.key === 'Escape' && setRejecting(false)}
              />
              <button
                disabled={busy}
                onClick={() => reject.mutate({ id: current.id, reason: reason.trim() || null }, { onSuccess: setCurrent })}
                className="rounded-md bg-slate-700 px-2.5 py-1 text-xs text-white disabled:opacity-50"
              >
                Reddet
              </button>
              <button onClick={() => setRejecting(false)} className="text-xs text-slate-500">Vazgeç</button>
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <button
                disabled={busy}
                onClick={() => approve.mutate({ id: current.id, rememberAuto: remember }, { onSuccess: setCurrent })}
                className="rounded-md bg-green-600 px-3 py-1 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-50"
              >
                {approve.isPending ? 'Yapılıyor…' : 'Onayla'}
              </button>
              <button
                disabled={busy}
                onClick={() => setRejecting(true)}
                className="rounded-md px-3 py-1 text-xs text-slate-600 ring-1 ring-slate-300 hover:bg-slate-50 disabled:opacity-50"
              >
                Reddet
              </button>
              <label className="ml-auto flex items-center gap-1 text-[11px] text-slate-500">
                <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
                Bu tür işlemleri bundan sonra otomatik yap
              </label>
            </div>
          )}
          {error && <p className="text-xs text-red-700">{error}</p>}
        </div>
      )}
    </div>
  )
}
