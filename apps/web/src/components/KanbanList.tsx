import { memo, useState, type FormEvent } from 'react'
import { SortableContext, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import type { BoardList, CardSummary, Label } from '../lib/types'
import CardFace from './CardFace'
import WhenBadge from './WhenBadge'
import { useParseTitle, type NewCardInput } from '../api/boards'
import { applyWhen } from '../lib/when'

export const cardKey = (id: number) => `card-${id}`
export const listKey = (id: number) => `list-${id}`

const SortableCard = memo(function SortableCard({
  card,
  labels,
  onOpen,
  tracking,
  onToggle,
}: {
  card: CardSummary
  labels: Map<number, Label>
  onOpen: (id: number) => void
  tracking: boolean
  onToggle: (card: CardSummary) => void
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: cardKey(card.id),
    data: { type: 'card' },
    transition: { duration: 180, easing: 'ease' },
  })
  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={isDragging ? 'opacity-40 [&>div]:border-dashed [&>div]:border-slate-400' : ''}
      {...attributes}
      {...listeners}
      onClick={() => onOpen(card.id)}
    >
      <CardFace card={card} labels={labels} tracking={tracking} onToggle={onToggle} />
    </li>
  )
})

/** Liste surukleme overlay'i: baslik + ilk 3 kartin ozeti. */
export function ListOverlay({
  list,
  cards,
  labels,
}: {
  list: BoardList
  cards: CardSummary[]
  labels: Map<number, Label>
}) {
  return (
    <section className="w-72 rotate-2 scale-[1.02] cursor-grabbing rounded-xl bg-slate-100/95 pb-2 shadow-[0_12px_32px_-8px_rgb(23_32_56/0.4)]">
      <h3 className="px-3 pt-3 pb-2 text-sm font-medium">
        {list.is_done_list && <span className="mr-1 text-green-600">✓</span>}
        {list.name}
        <span className="ml-2 text-xs font-normal text-slate-400">{cards.length}</span>
      </h3>
      <ul className="flex flex-col gap-2 px-2">
        {cards.slice(0, 3).map((c) => (
          <li key={c.id}>
            <CardFace card={c} labels={labels} />
          </li>
        ))}
      </ul>
      {cards.length > 3 && <p className="px-3 pt-2 text-xs text-slate-500">+{cards.length - 3} kart daha</p>}
    </section>
  )
}

interface Props {
  list: BoardList
  cards: CardSummary[]
  labels: Map<number, Label>
  /** Kronometresi calisan kartin id'si (BoardPage tek yerde okur; 9c). */
  trackingCardId: number | null
  onOpenCard: (id: number) => void
  onToggleCard: (card: CardSummary) => void
  onAddCard: (listId: number, data: NewCardInput, schedule: boolean) => void
  onRename: (listId: number, name: string) => void
  onToggleDone: (listId: number, isDone: boolean) => void
  onDelete: (listId: number) => void
}

/** Surukleme sirasinda yalniz icerigi degisen liste yeniden cizilsin: cards dizisi sig karsilastirilir. */
function areEqual(a: Props, b: Props) {
  if (a.cards.length !== b.cards.length || !a.cards.every((c, i) => c === b.cards[i])) return false
  return (
    a.list === b.list &&
    a.labels === b.labels &&
    a.trackingCardId === b.trackingCardId &&
    a.onOpenCard === b.onOpenCard &&
    a.onToggleCard === b.onToggleCard &&
    a.onAddCard === b.onAddCard &&
    a.onRename === b.onRename &&
    a.onToggleDone === b.onToggleDone &&
    a.onDelete === b.onDelete
  )
}

function KanbanList({
  list,
  cards,
  labels,
  trackingCardId,
  onOpenCard,
  onToggleCard,
  onAddCard,
  onRename,
  onToggleDone,
  onDelete,
}: Props) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: listKey(list.id),
    data: { type: 'list' },
    transition: { duration: 180, easing: 'ease' },
  })
  const [adding, setAdding] = useState(false)
  const [title, setTitle] = useState('')
  const [dismissed, setDismissed] = useState<string | null>(null)
  const [schedule, setSchedule] = useState(false)
  const { match, ready } = useParseTitle(adding ? title : '')
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(list.name)
  const [menu, setMenu] = useState(false)

  function submitCard(e: FormEvent) {
    e.preventDefault()
    if (!title.trim()) return
    const data = applyWhen(title, match, ready, dismissed)
    onAddCard(list.id, data, schedule && 'due_date' in data && !!data.estimated_minutes)
    setTitle('')
    setDismissed(null)
    setSchedule(false)
  }

  function closeAdd() {
    setAdding(false)
    setDismissed(null)
    setSchedule(false)
  }

  function submitName(e?: FormEvent) {
    e?.preventDefault()
    setEditing(false)
    if (name.trim() && name.trim() !== list.name) onRename(list.id, name.trim())
    else setName(list.name)
  }

  return (
    <section
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`flex max-h-full w-72 shrink-0 flex-col rounded-xl bg-slate-100/95 ${isDragging ? 'opacity-40' : ''}`}
    >
      <header className="relative flex items-center gap-2 px-3 pt-3 pb-2" {...attributes} {...listeners}>
        {editing ? (
          <form onSubmit={submitName} className="flex-1">
            <input
              autoFocus
              className="w-full rounded border border-slate-300 px-1.5 py-0.5 text-sm font-medium"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onBlur={() => submitName()}
              onPointerDown={(e) => e.stopPropagation()}
              onKeyDown={(e) => e.stopPropagation()}
            />
          </form>
        ) : (
          <h3
            className="flex-1 cursor-grab text-sm font-medium"
            onDoubleClick={() => setEditing(true)}
            title="Yeniden adlandırmak için çift tıkla"
          >
            {list.is_done_list && <span className="mr-1 text-green-600">✓</span>}
            {list.name}
            <span className="ml-2 text-xs font-normal text-slate-400">{cards.length}</span>
          </h3>
        )}
        <button
          aria-label="Liste menüsü"
          className="rounded px-1.5 text-slate-500 hover:bg-slate-200"
          onPointerDown={(e) => e.stopPropagation()}
          onClick={() => setMenu((m) => !m)}
        >
          ⋯
        </button>
        {menu && (
          <div
            className="absolute top-9 right-2 z-10 w-56 rounded-lg bg-surface py-1 text-sm shadow-lg ring-1 ring-slate-200"
            onPointerDown={(e) => e.stopPropagation()}
          >
            <button className="block w-full px-3 py-1.5 text-left hover:bg-slate-100" onClick={() => { setMenu(false); setEditing(true) }}>
              Yeniden adlandır
            </button>
            <button className="block w-full px-3 py-1.5 text-left hover:bg-slate-100" onClick={() => { setMenu(false); onToggleDone(list.id, !list.is_done_list) }}>
              {list.is_done_list ? '"Tamamlandı" listesi olmaktan çıkar' : '"Tamamlandı" listesi yap'}
            </button>
            <button
              className="block w-full px-3 py-1.5 text-left text-red-600 hover:bg-red-50 disabled:text-slate-300"
              disabled={cards.length > 0}
              title={cards.length > 0 ? 'Önce kartları taşı' : undefined}
              onClick={() => { setMenu(false); onDelete(list.id) }}
            >
              Listeyi sil
            </button>
          </div>
        )}
      </header>

      <SortableContext items={cards.map((c) => cardKey(c.id))} strategy={verticalListSortingStrategy}>
        <ul className="flex min-h-2 flex-col gap-2 overflow-y-auto px-2 pb-2">
          {cards.map((c) => (
            <SortableCard
              key={c.id}
              card={c}
              labels={labels}
              tracking={trackingCardId === c.id}
              onOpen={onOpenCard}
              onToggle={onToggleCard}
            />
          ))}
        </ul>
      </SortableContext>

      <div className="px-2 pb-2">
        {adding ? (
          <form onSubmit={submitCard} className="space-y-2">
            <textarea
              autoFocus
              rows={2}
              className="w-full resize-none rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
              placeholder="Kart başlığı… (Enter: ekle, Esc: kapat)"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) submitCard(e)
                if (e.key === 'Escape') closeAdd()
              }}
            />
            {match && match.phrase !== dismissed && (
              <WhenBadge
                match={match}
                onDismiss={() => setDismissed(match.phrase)}
                schedule={{ checked: schedule, onChange: setSchedule }}
              />
            )}
            <div className="flex gap-2">
              <button className="rounded-md bg-slate-900 px-3 py-1 text-sm text-on-ink">Ekle</button>
              <button type="button" className="text-sm text-slate-500" onClick={closeAdd}>
                Vazgeç
              </button>
            </div>
          </form>
        ) : (
          <button
            className="w-full rounded-lg px-2 py-1.5 text-left text-sm text-slate-500 hover:bg-slate-200"
            onClick={() => setAdding(true)}
          >
            + Kart ekle
          </button>
        )}
      </div>
    </section>
  )
}

export default memo(KanbanList, areEqual)
