import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import { SortableContext, arrayMove, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { useQueryClient } from '@tanstack/react-query'
import { Check, GripVertical, Hourglass, MoreHorizontal, Play, Plus, Square, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { parseTitleNow } from '../api/boards'
import { localDay, shiftDay, useDayPlanMutations } from '../api/dayPlans'
import { useActiveSession, useSessionMutations } from '../api/sessions'
import { formatDuration } from '../lib/format'
import type { BoardWithCounts, DayPlan, DayPlanItem, PlanSuggestion } from '../lib/types'

/** Plan maddesindeki kart icin kronometre: istedigin an basla / durdur. */
function PlayButton({ cardId, title }: { cardId: number; title: string }) {
  const active = useActiveSession()
  const m = useSessionMutations()
  const running = active.data?.card_id === cardId
  return (
    <button
      onClick={() => (running ? m.stop.mutate() : m.start.mutate(cardId))}
      disabled={m.start.isPending || m.stop.isPending}
      aria-label={running ? `${title} için kronometreyi durdur` : `${title} için çalışmaya başla`}
      title={running ? 'Durdur' : active.data ? 'Çalışan süre durur, bu kart başlar' : 'Çalışmaya başla'}
      className={`rounded p-1 ${running ? 'text-[var(--color-rec)]' : 'text-slate-400 hover:text-slate-900'} disabled:opacity-50`}
    >
      {running ? <Square size={13} fill="currentColor" aria-hidden /> : <Play size={14} aria-hidden />}
    </button>
  )
}

/** Plandaki bir madde (kaydedilmeden onceki taslak). */
interface Draft {
  key: string
  id: number | null
  card_id: number | null
  event_id: number | null
  title: string
  board_id: number | null
  planned_minutes: number | null
  planned_start: string | null
  outcome: DayPlanItem['outcome'] | null
  card_status: DayPlanItem['card_status'] | null
  hint?: string
  warn?: boolean
}

const KIND_LABEL: Record<PlanSuggestion['kind'], string> = {
  event: 'Takvimde',
  carry_over: 'Ertelenen',
  next_in_chain: 'Sıradaki',
  due: 'Son tarihi bugün',
  overdue: 'Gecikmiş',
  in_progress: 'Devam eden',
  worked: 'Üzerinde çalışılan',
}

/** Oneri <-> taslak eslestirmesi icin referans (satir anahtari degil). */
const refOf = (s: { card_id?: number | null; event_id?: number | null; title: string }) =>
  s.event_id != null ? `e${s.event_id}` : s.card_id != null ? `c${s.card_id}` : `t${s.title.trim().toLocaleLowerCase('tr')}`

const isDone = (d: Draft) => d.outcome === 'done' || d.card_status === 'completed'

const hideUntilHover = 'opacity-0 group-hover:opacity-100 focus:opacity-100 [@media(hover:none)]:opacity-100'

const timeFmt = new Intl.DateTimeFormat('tr-TR', { hour: '2-digit', minute: '2-digit' })

interface RowProps {
  d: Draft
  color?: string
  dirty: boolean
  menuOpen: boolean
  boards: BoardWithCounts[]
  busy: boolean
  error?: string
  onToggleDone: (checked: boolean) => void
  onMinutes: (v: number | null) => void
  onRemove: () => void
  onMenu: (open: boolean) => void
  onToCard: (boardId: number) => void
  onMove: () => void
  moveLabel: string
}

function PlanRow({ d, color, dirty, menuOpen, boards, busy, error, onToggleDone, onMinutes, onRemove, onMenu, onToCard, onMove, moveLabel }: RowProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: d.key })
  const [convert, setConvert] = useState(false)
  const [boardId, setBoardId] = useState<number | null>(d.board_id ?? boards[0]?.id ?? null)
  const menuRef = useRef<HTMLDivElement>(null)
  const onMenuRef = useRef(onMenu)
  onMenuRef.current = onMenu
  const saved = d.id != null
  const done = isDone(d)

  useEffect(() => {
    if (!menuOpen) {
      setConvert(false)
      return
    }
    const onDoc = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) onMenuRef.current(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onMenuRef.current(false)
    }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [menuOpen])

  const menuItem = 'w-full rounded px-2 py-1.5 text-left text-[14px] hover:bg-slate-100 disabled:opacity-50'
  const locked = !saved || dirty

  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`group relative py-2 text-[15px] ${isDragging ? 'opacity-60' : ''}`}
    >
      <div className="flex items-center gap-2">
        <button
          type="button"
          {...attributes}
          {...listeners}
          aria-label={`${d.title} sırasını değiştir`}
          className={`cursor-grab rounded p-0.5 text-slate-400 hover:text-slate-700 ${hideUntilHover}`}
        >
          <GripVertical size={14} aria-hidden />
        </button>
        <input
          type="checkbox"
          className="size-4 accent-green-700"
          aria-label={`${d.title} tamamlandı`}
          checked={done}
          disabled={!saved || busy}
          title={saved ? undefined : 'Önce planı kaydet'}
          onChange={(e) => onToggleDone(e.target.checked)}
        />
        <span aria-hidden className="h-5 w-1 shrink-0 rounded-full" style={{ backgroundColor: color ?? 'var(--color-slate-300)' }} />
        <span className={`flex-1 ${done ? 'text-slate-500 line-through' : ''}`}>
          {d.title}
          {d.warn && (
            <span className="ml-2 rounded bg-amber-100 px-1.5 text-[12px] text-amber-900" title="Başlıkta başka bir gün geçiyor; madde bu günün planında">
              başlıkta başka gün
            </span>
          )}
        </span>
        {d.card_id != null && <PlayButton cardId={d.card_id} title={d.title} />}
        {d.hint && <span className="text-[13px] text-slate-500">{d.hint}</span>}
        <input
          type="number"
          min={0}
          step={5}
          title="Planlanan dakika"
          aria-label={`${d.title} için planlanan dakika`}
          className="w-16 rounded border border-slate-300 bg-surface px-1.5 py-0.5 text-right text-[13px] tabular-nums"
          value={d.planned_minutes ?? ''}
          placeholder="dk"
          onChange={(e) => onMinutes(e.target.value === '' ? null : Number(e.target.value))}
        />
        <div className="relative" ref={menuRef}>
          <button
            type="button"
            onClick={() => onMenu(!menuOpen)}
            aria-label={`${d.title} için işlemler`}
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            className={`rounded p-0.5 text-slate-400 hover:text-slate-900 ${hideUntilHover}`}
          >
            <MoreHorizontal size={16} aria-hidden />
          </button>
          {menuOpen && (
            <div role="menu" className="absolute right-0 z-10 mt-1 w-56 rounded-md border border-slate-200 bg-surface p-1 shadow-md">
              {convert ? (
                <div className="flex items-center gap-1 p-1">
                  <select
                    aria-label="Board"
                    className="min-w-0 flex-1 rounded border border-slate-300 bg-surface px-1 py-1 text-[13px]"
                    value={boardId ?? ''}
                    onChange={(e) => setBoardId(Number(e.target.value))}
                  >
                    {boards.map((b) => (
                      <option key={b.id} value={b.id}>{b.name}</option>
                    ))}
                  </select>
                  <button
                    type="button"
                    disabled={boardId == null || busy}
                    onClick={() => boardId != null && onToCard(boardId)}
                    className="rounded bg-slate-900 px-2 py-1 text-[13px] text-on-ink disabled:opacity-50"
                  >
                    Dönüştür
                  </button>
                </div>
              ) : (
                <>
                  {d.card_id == null && boards.length > 0 && (
                    <button type="button" role="menuitem" className={menuItem} disabled={locked} onClick={() => setConvert(true)}>
                      Karta dönüştür
                    </button>
                  )}
                  {!done && (
                    <button
                      type="button"
                      role="menuitem"
                      className={menuItem}
                      disabled={locked || busy}
                      onClick={() => {
                        if (d.event_id != null && !confirm('Takvimdeki etkinlik yerinde kalır. Madde taşınsın mı?')) return
                        onMove()
                      }}
                    >
                      {moveLabel}
                    </button>
                  )}
                  {locked && <p className="px-2 pb-1 text-[12px] text-slate-500">Önce planı kaydet</p>}
                </>
              )}
            </div>
          )}
        </div>
        <button onClick={onRemove} className="rounded p-0.5 text-slate-400 hover:text-red-700" aria-label={`${d.title} plandan çıkar`}>
          <X size={15} aria-hidden />
        </button>
      </div>
      {error && <p className="mt-1 pl-8 text-[13px] text-red-700">{error}</p>}
    </li>
  )
}

export default function PlanEditor({
  day,
  plan,
  suggestions,
  boards,
}: {
  day: string
  plan: DayPlan
  suggestions: PlanSuggestion[]
  boards: Map<number, BoardWithCounts>
}) {
  const m = useDayPlanMutations(day)
  // Gecmis gune tasima 422 verir (D7): hedef en erken bugun
  const today = localDay()
  const moveTarget = shiftDay(day, 1) < today ? today : shiftDay(day, 1)
  const moveLabel = moveTarget === today ? 'Bugüne taşı' : moveTarget === shiftDay(today, 1) ? 'Yarına taşı' : 'Sonraki güne taşı'
  const qc = useQueryClient()
  const [draft, setDraft] = useState<Draft[]>([])
  const [free, setFree] = useState('')
  const [freeBusy, setFreeBusy] = useState(false)
  const [dirty, setDirtyState] = useState(false)
  const [openMenu, setOpenMenu] = useState<string | null>(null)
  const [rowError, setRowError] = useState<{ key: string; msg: string } | null>(null)
  const dirtyRef = useRef(false)
  // Kirli taslakta kullanicinin bu oturumda cikardigi sunucu satirlari (D1)
  const removedIds = useRef(new Set<number>())
  const busyRef = useRef(false)
  const seq = useRef(0)
  const setDirty = (v: boolean) => {
    dirtyRef.current = v
    setDirtyState(v)
  }

  // Sunucudaki plan degisince: temizse taslagi bastan kur; kirliyse yalniz durum alanlarini tazele
  useEffect(() => {
    const items = plan.items.filter((i) => i.was_planned)
    if (!dirtyRef.current) {
      removedIds.current.clear()
      setDraft(
        items.map((i) => ({
          key: `i${i.id}`,
          id: i.id,
          card_id: i.card_id,
          event_id: i.event_id,
          title: i.title,
          board_id: i.board_id,
          planned_minutes: i.planned_minutes,
          planned_start: i.planned_start,
          outcome: i.outcome,
          card_status: i.card_status ?? null,
          hint: i.planned_start ? timeFmt.format(new Date(i.planned_start)) : undefined,
        })),
      )
      return
    }
    const byId = new Map(items.map((i) => [i.id, i]))
    setDraft((cur) => {
      const known = new Set(cur.map((d) => d.id).filter((x): x is number => x != null))
      const refreshed = cur.map((d) => {
        const s = d.id != null ? byId.get(d.id) : undefined
        return s ? { ...d, outcome: s.outcome, card_status: s.card_status ?? null } : d
      })
      // Baska yerden (asistan, takvim) eklenen satirlar taslakta yoksa kaydetmede silinirdi (D1)
      const added: Draft[] = items
        .filter((i) => !known.has(i.id) && !removedIds.current.has(i.id))
        .map((i) => ({
          key: `i${i.id}`,
          id: i.id,
          card_id: i.card_id,
          event_id: i.event_id,
          title: i.title,
          board_id: i.board_id,
          planned_minutes: i.planned_minutes,
          planned_start: i.planned_start,
          outcome: i.outcome,
          card_status: i.card_status ?? null,
          hint: i.planned_start ? timeFmt.format(new Date(i.planned_start)) : undefined,
        }))
      return added.length ? [...refreshed, ...added] : refreshed
    })
  }, [plan])

  const inDraft = useMemo(() => new Set(draft.map((d) => refOf(d))), [draft])
  const total = draft.reduce((s, d) => s + (d.planned_minutes ?? 0), 0)
  const activeBoards = useMemo(() => [...boards.values()].filter((b) => !b.is_archived), [boards])

  const update = (fn: (d: Draft[]) => Draft[]) => {
    setDraft(fn)
    setDirty(true)
  }

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  function onDragEnd(e: DragEndEvent) {
    const { active, over } = e
    if (!over || active.id === over.id) return
    update((d) => {
      const from = d.findIndex((x) => x.key === active.id)
      const to = d.findIndex((x) => x.key === over.id)
      return from < 0 || to < 0 ? d : arrayMove(d, from, to)
    })
  }

  function toggle(s: PlanSuggestion) {
    const ref = refOf(s)
    if (inDraft.has(ref)) {
      const first = draft.find((x) => refOf(x) === ref)
      if (first?.id != null) removedIds.current.add(first.id)
      return update((d) => d.filter((x) => x !== first))
    }
    update((d) => [
      ...d,
      {
        key: `n${++seq.current}`,
        id: null,
        card_id: s.card_id ?? null,
        event_id: s.event_id ?? null,
        title: s.title,
        board_id: s.board_id ?? null,
        planned_minutes: s.planned_minutes ?? null,
        planned_start: s.planned_start ?? null,
        outcome: null,
        card_status: null,
        hint: s.planned_start ? timeFmt.format(new Date(s.planned_start)) : undefined,
      },
    ])
  }

  async function addFree(e: FormEvent) {
    e.preventDefault()
    const raw = free.trim()
    if (!raw || busyRef.current) return
    busyRef.current = true
    setFreeBusy(true)
    try {
      let title = raw
      let minutes: number | null = null
      let start: string | null = null
      let hint: string | undefined
      let warn = false
      const mt = await parseTitleNow(qc, raw)
      if (mt && mt.strong) {
        if (!mt.due_date) {
          title = mt.clean_title || raw
          minutes = mt.estimated_minutes ?? null
        } else if (localDay(new Date(mt.due_date)) === day) {
          title = mt.clean_title || raw
          if (mt.has_time) {
            start = mt.due_date
            hint = timeFmt.format(new Date(mt.due_date))
          }
          minutes = mt.estimated_minutes ?? null
        } else {
          warn = true
        }
      }
      update((d) => [
        ...d,
        { key: `n${++seq.current}`, id: null, card_id: null, event_id: null, title, board_id: null, planned_minutes: minutes, planned_start: start, outcome: null, card_status: null, hint, warn },
      ])
      setFree('')
    } finally {
      busyRef.current = false
      setFreeBusy(false)
    }
  }

  function save() {
    m.save.mutate(
      draft.map((d) => ({
        id: d.id,
        card_id: d.card_id,
        event_id: d.event_id,
        title: d.card_id == null && d.event_id == null ? d.title : null,
        planned_minutes: d.planned_minutes,
        ...(d.planned_start != null && d.event_id == null ? { planned_start: d.planned_start } : {}),
      })),
      {
        onSuccess: () => {
          removedIds.current.clear()
          setDirty(false)
        },
      },
    )
  }

  const fail = (key: string) => (err: Error) => setRowError({ key, msg: err.message })

  const grouped = (Object.keys(KIND_LABEL) as PlanSuggestion['kind'][])
    .map((kind) => ({ kind, items: suggestions.filter((s) => s.kind === kind) }))
    .filter((g) => g.items.length > 0)

  return (
    <div className="grid gap-x-12 gap-y-10 lg:grid-cols-2">
      <section>
        <h2 className="text-[22px]">Öneriler</h2>
        <p className="mt-1 mb-4 text-[15px] text-slate-600">Takvimden, son tarihlerden ve ertelenenlerden toplandı. Plana eklemek için tıkla.</p>
        {grouped.length === 0 && <p className="text-[15px] text-slate-500">Bu gün için öneri yok; planı sağdan kendin yaz.</p>}
        {grouped.map((g) => (
          <div key={g.kind} className="mb-5">
            <h3 className="mb-1 text-[14px] font-semibold text-slate-700">{KIND_LABEL[g.kind]}</h3>
            <ul className="space-y-1">
              {g.items.map((s) => {
                const on = inDraft.has(refOf(s))
                const board = s.board_id != null ? boards.get(s.board_id) : undefined
                return (
                  <li key={`${refOf(s)}-${s.kind}`}>
                    <button
                      onClick={() => toggle(s)}
                      aria-pressed={on}
                      className={`flex w-full items-center gap-2 rounded-md border border-l-4 px-2.5 py-2 text-left text-[15px] ${on ? 'border-blue-600 bg-blue-50' : 'border-slate-200 bg-surface hover:border-slate-400'}`}
                      style={{ borderLeftColor: board?.color ?? '#cbd5e1' }}
                    >
                      {on ? <Check size={15} className="shrink-0 text-blue-700" aria-hidden /> : <Plus size={15} className="shrink-0 text-slate-400" aria-hidden />}
                      <span className={`flex-1 ${s.blocked ? 'text-slate-500' : ''}`}>{s.title}</span>
                      {s.blocked && <span className="inline-flex items-center gap-0.5 text-[12px] text-amber-800"><Hourglass size={12} aria-hidden />Bekliyor</span>}
                      {s.planned_start && <span className="text-[13px] text-slate-600 tabular-nums">{timeFmt.format(new Date(s.planned_start))}</span>}
                      {s.planned_minutes != null && <span className="text-[13px] text-slate-500 tabular-nums">{formatDuration(s.planned_minutes * 60)}</span>}
                    </button>
                  </li>
                )
              })}
            </ul>
          </div>
        ))}
      </section>

      <section className="self-start lg:sticky lg:top-6 lg:border-l lg:border-slate-200 lg:pl-8">
        <div className="mb-3 flex items-baseline justify-between gap-3">
          <h2 className="text-[22px]">Planın</h2>
          <span className="text-[14px] text-slate-600 tabular-nums">{draft.length} madde, {formatDuration(total * 60)}</span>
        </div>
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
          <SortableContext items={draft.map((d) => d.key)} strategy={verticalListSortingStrategy}>
            <ul className="divide-y divide-slate-200 border-y border-slate-200">
              {draft.map((d) => (
                <PlanRow
                  key={d.key}
                  d={d}
                  color={d.board_id != null ? boards.get(d.board_id)?.color : undefined}
                  dirty={dirty}
                  menuOpen={openMenu === d.key}
                  onMenu={(open) => setOpenMenu(open ? d.key : null)}
                  boards={activeBoards}
                  busy={m.patchItem.isPending || m.toCard.isPending || m.moveItem.isPending}
                  error={rowError?.key === d.key ? rowError.msg : undefined}
                  onToggleDone={(checked) => {
                    setRowError(null)
                    if (d.id != null) m.patchItem.mutate({ id: d.id, body: { done: checked } }, { onError: fail(d.key) })
                  }}
                  onMinutes={(v) => update((all) => all.map((x) => (x.key === d.key ? { ...x, planned_minutes: v } : x)))}
                  onRemove={() => {
                    if (d.id != null) removedIds.current.add(d.id)
                    update((all) => all.filter((x) => x.key !== d.key))
                  }}
                  onToCard={(board_id) => {
                    setRowError(null)
                    if (d.id != null) m.toCard.mutate({ id: d.id, body: { board_id } }, { onSuccess: () => setOpenMenu(null), onError: fail(d.key) })
                  }}
                  moveLabel={moveLabel}
                  onMove={() => {
                    setOpenMenu(null)
                    setRowError(null)
                    if (d.id != null) m.moveItem.mutate({ id: d.id, body: { date: moveTarget } }, { onError: fail(d.key) })
                  }}
                />
              ))}
            </ul>
          </SortableContext>
        </DndContext>
        {draft.length === 0 && <p className="py-3 text-[15px] text-slate-500">Henüz madde yok. Önerilerden ekle ya da aşağıya yaz.</p>}
        <form onSubmit={addFree} className="mt-2 flex items-center gap-2 border-b border-slate-200 pb-2">
          <Plus size={16} className="text-slate-400" aria-hidden />
          <input className="flex-1 bg-transparent py-1 text-[15px] placeholder:text-slate-400 focus:outline-none" maxLength={200} aria-label="Karta bağlı olmayan madde" placeholder="Karta bağlı olmayan bir madde yaz" value={free} readOnly={freeBusy} aria-busy={freeBusy} onChange={(e) => setFree(e.target.value)} />
        </form>
        <div className="mt-4 flex items-center justify-end gap-3">
          {m.save.isSuccess && !dirty && <span className="text-[14px] text-green-700">Plan kaydedildi</span>}
          {m.save.error && <span className="text-[14px] text-red-700">{m.save.error.message}</span>}
          <button onClick={save} disabled={m.save.isPending || (!dirty && plan.exists)} className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-on-ink disabled:opacity-50">
            Planı kaydet
          </button>
        </div>
      </section>
    </div>
  )
}
