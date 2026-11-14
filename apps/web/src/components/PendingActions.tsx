import { useState } from 'react'
import { useMutationState } from '@tanstack/react-query'
import { ApiError } from '../lib/api'
import { DECISION_KEY, usePendingMcpActions } from '../api/assistant'
import ActionCard from './ActionCard'

/**
 * Bekleyen işlemler (Faz 13i): Claude (Claude Desktop / Claude Code) bağlantısının önerdiği,
 * henüz onaylanmamış işlemler. Sohbete bağlı olmayan `proposed` satırlar; panel açıkken 30 sn'de
 * bir ve pencere odaklanınca tazelenir. İşlem onaylanana kadar YAPILMAMIŞTIR.
 */
export default function PendingActions() {
  const pending = usePendingMcpActions()
  const [dismissedAt, setDismissedAt] = useState(0)
  // 409: işlem başka yerden (ör. başka sekme) sonuçlanmış; kart listeden düşer, kısa bir not kalır
  const conflicts = useMutationState({
    filters: { mutationKey: DECISION_KEY, status: 'error' },
    select: (m) => ({ error: m.state.error, at: m.state.submittedAt }),
  })
  const conflicted = conflicts.some((c) => c.error instanceof ApiError && c.error.status === 409 && c.at > dismissedAt)

  const items = pending.data ?? []
  if (items.length === 0 && !conflicted) return null

  return (
    <section aria-label="Bekleyen işlemler" className="border-b border-amber-200 bg-amber-50/60 px-3 py-2">
      <h3 className="mb-1.5 text-xs font-semibold text-amber-900">
        Bekleyen işlemler{items.length > 0 ? ` (${items.length})` : ''}
      </h3>
      {conflicted && (
        <p role="status" className="mb-1.5 flex items-center justify-between gap-2 rounded-md bg-surface px-2 py-1 text-xs text-slate-600">
          Bu işlem başka yerden sonuçlanmış.
          <button type="button" onClick={() => setDismissedAt(Date.now())} className="underline">
            Tamam
          </button>
        </p>
      )}
      <ul className="max-h-64 space-y-1.5 overflow-y-auto">
        {items.map((a) => (
          <li key={a.id}>
            {a.model_id?.startsWith('mcp:') && (
              <span className="mb-0.5 inline-block rounded-full bg-slate-200 px-2 py-0.5 text-[11px] text-slate-700">Claude</span>
            )}
            <ActionCard action={a} />
          </li>
        ))}
      </ul>
    </section>
  )
}
