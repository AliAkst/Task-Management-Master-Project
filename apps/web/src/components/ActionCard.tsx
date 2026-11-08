import { useState } from 'react'
import { useActionDecision, type AiAction } from '../api/assistant'

const STATUS: Record<AiAction['status'], { label: string; cls: string }> = {
  proposed: { label: 'Onay bekliyor', cls: 'bg-amber-100 text-amber-800' },
  executed: { label: '✅ Yapıldı', cls: 'bg-green-100 text-green-800' },
  rejected: { label: '✗ Reddedildi', cls: 'bg-slate-200 text-slate-600' },
  failed: { label: '⚠️ Başarısız', cls: 'bg-red-100 text-red-700' },
}

/** Madde madde onaylanan islemlerde (Gelen Kutusu dagitimi) tek tek cikarilabilen satir. */
export interface ActionItem {
  id: number
  title: string
  detail: string
  reason?: string | null
}

/**
 * AI'in yazma islemi. "Onay bekliyor" ise islem YAPILMAMISTIR; kullanici onaylarsa
 * yapilir. "Bu tür işlemleri otomatik yap" secilirse izin ayari 'auto' olur.
 * `items` verilirse maddeler onay kutusuyla listelenir; isaretlenmeyenler cikarilir.
 */
export default function ActionCard({ action, items }: { action: AiAction; items?: ActionItem[] }) {
  const { approve, reject } = useActionDecision()
  const [current, setCurrent] = useState(action)
  const [remember, setRemember] = useState(false)
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const [skipped, setSkipped] = useState<Set<number>>(new Set())
  const busy = approve.isPending || reject.isPending
  const error = (approve.error ?? reject.error)?.message
  const status = STATUS[current.status]
  const failure = current.status === 'failed' ? String(current.result?.error ?? '') : null
  const proposed = current.status === 'proposed'
  const selectable = !!items?.length && proposed
  const remaining = items ? items.length - skipped.size : 0
  // Madde listesi varken ozetin ilk satiri baslik; maddeler asagida ayri gosterilir
  const summary = items?.length ? current.summary.split('\n')[0] : current.summary
  const result = current.result as { moved?: unknown[]; skipped?: unknown[]; failed?: unknown[] } | null

  function toggle(id: number) {
    setSkipped((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <div className={`rounded-xl border bg-white p-2.5 text-sm ${proposed ? 'border-amber-300' : 'border-slate-200'}`}>
      <div className="flex items-start gap-2">
        <span className="flex-1 whitespace-pre-line">{summary}</span>
        <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] ${status.cls}`}>{status.label}</span>
      </div>
      {items && items.length > 0 && (
        <ul className="mt-2 divide-y divide-slate-200 border-y border-slate-200">
          {items.map((it) => {
            const off = selectable && skipped.has(it.id)
            return (
              <li key={it.id} className="py-1.5">
                <label className={`flex items-start gap-2 ${selectable ? 'cursor-pointer' : ''}`}>
                  {selectable && (
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={!off}
                      onChange={() => toggle(it.id)}
                      aria-label={`${it.title} taşınsın`}
                    />
                  )}
                  <span className={off ? 'text-slate-400 line-through' : ''}>
                    <span className="font-medium">{it.title}</span>
                    <span className="text-slate-600"> → {it.detail}</span>
                    {it.reason && <span className="block text-[13px] text-slate-500">{it.reason}</span>}
                  </span>
                </label>
              </li>
            )
          })}
        </ul>
      )}
      {current.status === 'executed' && result && ((result.skipped?.length ?? 0) > 0 || (result.failed?.length ?? 0) > 0) && (
        <p className="mt-1 text-xs text-slate-500">
          {result.moved?.length ?? 0} taşındı
          {(result.skipped?.length ?? 0) > 0 && `, ${result.skipped?.length} kart arada başka yere taşındığı için atlandı`}
          {(result.failed?.length ?? 0) > 0 && `, ${result.failed?.length} taşınamadı`}
        </p>
      )}
      {failure && <p className="mt-1 text-xs text-red-700">{failure}</p>}
      {current.status === 'rejected' && current.user_feedback && (
        <p className="mt-1 text-xs text-slate-500">Nedenin: {current.user_feedback}</p>
      )}

      {proposed && (
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
                disabled={busy || (selectable && remaining === 0)}
                onClick={() =>
                  approve.mutate(
                    { id: current.id, rememberAuto: remember, excludeCardIds: [...skipped] },
                    { onSuccess: setCurrent },
                  )
                }
                className="rounded-md bg-green-600 px-3 py-1 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-50"
              >
                {approve.isPending
                  ? 'Yapılıyor…'
                  : selectable && skipped.size > 0
                    ? `Seçili ${remaining} kartı onayla`
                    : 'Onayla'}
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
