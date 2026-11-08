import { useEffect, useMemo, useRef, useState } from 'react'
import { useQueries } from '@tanstack/react-query'
import { Play, Search, X } from 'lucide-react'
import { keys as boardKeys, useBoards } from '../api/boards'
import { localDay, useDayPlan } from '../api/dayPlans'
import { useSessionMutations } from '../api/sessions'
import { api } from '../lib/api'
import type { BoardDetail } from '../lib/types'
import { FOCUS_OPTIONS, useFocusPrefs } from '../stores/focus'

interface Option {
  cardId: number
  title: string
  board: string
  color: string
}

/**
 * "Neye calisiyorsun?" secicisi (Focus To-Do gibi): once bugunun plani, sonra
 * tum acik kartlar; arama ile daralt, sec ve kronometre o kart icin baslasin.
 * Calisan bir sure varsa durdurulur ve yenisi baslar (sunucu tek aktif tutar).
 */
export default function FocusPicker({ onClose, currentCardId }: { onClose: () => void; currentCardId?: number | null }) {
  const [q, setQ] = useState('')
  const ref = useRef<HTMLDivElement>(null)
  const m = useSessionMutations()
  const boards = useBoards()
  const plan = useDayPlan(localDay())
  const { focusMinutes, setFocusMinutes } = useFocusPrefs()
  const details = useQueries({
    queries: (boards.data ?? []).map((b) => ({
      queryKey: boardKeys.board(b.id),
      queryFn: () => api<BoardDetail>(`/boards/${b.id}`),
    })),
  })

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    const onDown = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && onClose()
    window.addEventListener('keydown', onKey)
    window.addEventListener('mousedown', onDown)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('mousedown', onDown)
    }
  }, [onClose])

  const { today, rest } = useMemo(() => {
    const boardOf = new Map((boards.data ?? []).map((b) => [b.id, b]))
    const all: Option[] = details
      .flatMap((d) => d.data?.cards ?? [])
      .filter((c) => c.status !== 'completed' && !c.is_archived)
      .map((c) => ({
        cardId: c.id,
        title: c.title,
        board: boardOf.get(c.board_id ?? -1)?.name ?? '',
        color: boardOf.get(c.board_id ?? -1)?.color ?? 'var(--color-slate-300)',
      }))
    const planned = new Set(
      (plan.data?.items ?? []).filter((i) => i.card_id != null && i.card_status !== 'completed').map((i) => i.card_id!),
    )
    const match = (o: Option) => !q.trim() || o.title.toLocaleLowerCase('tr').includes(q.trim().toLocaleLowerCase('tr'))
    const visible = all.filter((o) => o.cardId !== currentCardId && match(o))
    return {
      today: visible.filter((o) => planned.has(o.cardId)),
      rest: visible.filter((o) => !planned.has(o.cardId)).slice(0, 40),
    }
  }, [details, boards.data, plan.data, q, currentCardId])

  const start = (cardId: number | null) => m.start.mutate(cardId, { onSuccess: onClose })
  const loading = details.some((d) => d.isLoading)

  const row = (o: Option) => (
    <li key={o.cardId}>
      <button
        onClick={() => start(o.cardId)}
        disabled={m.start.isPending}
        className="group flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[14px] hover:bg-slate-100 disabled:opacity-50"
      >
        <span aria-hidden className="h-4 w-1 shrink-0 rounded-full" style={{ backgroundColor: o.color }} />
        <span className="min-w-0 flex-1 truncate">{o.title}</span>
        <span className="shrink-0 text-[12px] text-slate-500">{o.board}</span>
        <Play size={13} className="shrink-0 text-slate-400 group-hover:text-slate-900" aria-hidden />
      </button>
    </li>
  )

  return (
    <div
      ref={ref}
      role="dialog"
      aria-label="Neye çalışıyorsun?"
      className="absolute bottom-0 left-full z-40 ml-3 flex max-h-[70vh] w-80 flex-col rounded-xl border border-slate-200 bg-white p-3 shadow-xl"
    >
      <div className="mb-2 flex items-center justify-between">
        <p className="font-display text-[17px] font-[650]">Neye çalışıyorsun?</p>
        <button onClick={onClose} aria-label="Kapat" className="rounded p-1 text-slate-500 hover:bg-slate-100">
          <X size={15} aria-hidden />
        </button>
      </div>
      <label className="mb-2 flex items-center gap-2 rounded-md border border-slate-300 px-2 py-1">
        <Search size={14} className="text-slate-400" aria-hidden />
        <input
          autoFocus
          className="min-w-0 flex-1 bg-transparent text-[14px] focus:outline-none"
          placeholder="Kart ara"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          aria-label="Kart ara"
        />
      </label>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {today.length > 0 && (
          <>
            <p className="px-2 pt-1 text-[12px] font-semibold text-slate-600">Bugünün planı</p>
            <ul>{today.map(row)}</ul>
          </>
        )}
        <p className="px-2 pt-2 text-[12px] font-semibold text-slate-600">Açık kartlar</p>
        {loading && <p className="px-2 py-1 text-[13px] text-slate-500">Yükleniyor…</p>}
        {!loading && rest.length === 0 && <p className="px-2 py-1 text-[13px] text-slate-500">Eşleşen kart yok.</p>}
        <ul>{rest.map(row)}</ul>
      </div>

      <div className="mt-2 space-y-2 border-t border-slate-200 pt-2">
        <div className="flex items-center gap-2 text-[13px]" role="radiogroup" aria-label="Odak süresi">
          <span className="text-slate-600">Odak süresi</span>
          {FOCUS_OPTIONS.map((v) => (
            <button
              key={String(v)}
              role="radio"
              aria-checked={focusMinutes === v}
              onClick={() => setFocusMinutes(v)}
              className={`rounded-md px-2 py-0.5 ${focusMinutes === v ? 'bg-slate-900 text-white' : 'text-slate-700 ring-1 ring-slate-300 hover:ring-slate-900'}`}
            >
              {v === null ? 'Kapalı' : `${v} dk`}
            </button>
          ))}
        </div>
        <button
          onClick={() => start(null)}
          disabled={m.start.isPending}
          className="w-full rounded-md px-2 py-1.5 text-left text-[13px] text-slate-600 hover:bg-slate-100"
        >
          Karta bağlamadan serbest çalış
        </button>
        {m.start.error && <p className="text-[13px] text-red-700">{m.start.error.message}</p>}
      </div>
    </div>
  )
}
