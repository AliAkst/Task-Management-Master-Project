import { useState, type FormEvent } from 'react'
import { SortableContext, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import type { BoardList, CardSummary, Label } from '../lib/types'
import CardFace from './CardFace'

export const cardKey = (id: number) => `card-${id}`
export const listKey = (id: number) => `list-${id}`

function SortableCard({
  card,
  labels,
  onOpen,
}: {
  card: CardSummary
  labels: Map<number, Label>
  onOpen: (id: number) => void
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: cardKey(card.id),
    data: { type: 'card' },
  })
  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={isDragging ? 'opacity-30' : ''}
      {...attributes}
      {...listeners}
      onClick={() => onOpen(card.id)}
    >
      <CardFace card={card} labels={labels} />
    </li>
  )
}

interface Props {
  list: BoardList
  cards: CardSummary[]
  labels: Map<number, Label>
  onOpenCard: (id: number) => void
  onAddCard: (listId: number, title: string) => void
  onRename: (listId: number, name: string) => void
  onToggleDone: (listId: number, isDone: boolean) => void
  onDelete: (listId: number) => void
}

export default function KanbanList({
  list,
  cards,
  labels,
  onOpenCard,
  onAddCard,
  onRename,
  onToggleDone,
  onDelete,
}: Props) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: listKey(list.id),
    data: { type: 'list' },
  })
  const [adding, setAdding] = useState(false)
  const [title, setTitle] = useState('')
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(list.name)
  const [menu, setMenu] = useState(false)

  function submitCard(e: FormEvent) {
    e.preventDefault()
    if (!title.trim()) return
    onAddCard(list.id, title.trim())
    setTitle('')
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
      className={`flex max-h-full w-72 shrink-0 flex-col rounded-xl bg-slate-100 ${isDragging ? 'opacity-40' : ''}`}
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
            className="absolute top-9 right-2 z-10 w-56 rounded-lg bg-white py-1 text-sm shadow-lg ring-1 ring-slate-200"
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
            <SortableCard key={c.id} card={c} labels={labels} onOpen={onOpenCard} />
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
                if (e.key === 'Escape') setAdding(false)
              }}
            />
            <div className="flex gap-2">
              <button className="rounded-md bg-slate-900 px-3 py-1 text-sm text-white">Ekle</button>
              <button type="button" className="text-sm text-slate-500" onClick={() => setAdding(false)}>
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
