import { lazy, Suspense, useEffect, useMemo, useRef, useState, type CSSProperties, type FormEvent } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useIsMutating } from '@tanstack/react-query'
import {
  defaultDropAnimationSideEffects,
  DndContext,
  DragOverlay,
  KeyboardSensor,
  MeasuringStrategy,
  PointerSensor,
  pointerWithin,
  rectIntersection,
  useSensor,
  useSensors,
  type CollisionDetection,
  type DragEndEvent,
  type DragOverEvent,
  type DragStartEvent,
} from '@dnd-kit/core'
import {
  arrayMove,
  horizontalListSortingStrategy,
  SortableContext,
  sortableKeyboardCoordinates,
} from '@dnd-kit/sortable'
import { useBoard, useBoardMutations, useDeleteBoard, useUpdateBoard } from '../api/boards'
import BoardForm, { COLORS } from '../components/BoardForm'
import CardFace from '../components/CardFace'
import CardModal from '../components/CardModal'
import InboxTriage from '../components/InboxTriage'
import KanbanList, { ListOverlay, listKey } from '../components/KanbanList'
import Modal from '../components/Modal'
import { Segmented } from '../components/Page'
import { useModels } from '../api/assistant'
import { Lock, Settings2, Sparkles } from 'lucide-react'
import type { CardSummary, Label } from '../lib/types'
import { readableTextOn } from '../lib/color'

// React Flow + dagre buyuk; sadece grafik gorunumu acilinca yuklenir
const GraphView = lazy(() => import('../components/GraphView'))

type Columns = Record<number, number[]> // listId -> sirali kart id'leri

const parseKey = (key: string | number) => {
  const [type, id] = String(key).split('-')
  return { type, id: Number(id) }
}

// Faz 8e: once imlec altindaki, yoksa kesisen hedef; liste surukleniyorsa yalniz listeler
const collisionDetection: CollisionDetection = (args) => {
  const activeIsList = String(args.active.id).startsWith('list-')
  const containers = args.droppableContainers.filter((c) =>
    activeIsList ? String(c.id).startsWith('list-') : true,
  )
  const a = { ...args, droppableContainers: containers }
  const hits = pointerWithin(a)
  const found = hits.length ? hits : rectIntersection(a)
  if (activeIsList) return found
  // kart: imlec bir kartin ustundeyse kart, degilse (bosluk/bos liste) liste hedefi
  const cardHits = found.filter((c) => String(c.id).startsWith('card-'))
  return cardHits.length ? cardHits : found
}

const reducedMotion = () =>
  typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

export default function BoardPage() {
  const boardId = Number(useParams().boardId)
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const openCardId = params.get('card') ? Number(params.get('card')) : null
  const view = params.get('view') === 'graph' ? 'graph' : 'kanban'
  // Gorunum (kanban/grafik) URL'de kalir; kart acip kapatmak onu bozmaz
  const viewParam: Record<string, string> = view === 'graph' ? { view: 'graph' } : {}
  const openCard = (id: number) => setParams({ ...viewParam, card: String(id) })
  const closeCard = () => setParams(viewParam)
  const setView = (v: 'kanban' | 'graph') => setParams(v === 'graph' ? { view: 'graph' } : {})
  const models = useModels()

  const board = useBoard(boardId)
  const m = useBoardMutations(boardId)
  const updateBoard = useUpdateBoard(boardId)
  const deleteBoard = useDeleteBoard()

  // --- surukle-birak icin yerel durum (sunucu verisinden turetilir) ---
  const [columns, setColumns] = useState<Columns>({})
  const [listOrder, setListOrder] = useState<number[]>([])
  const [activeKey, setActiveKey] = useState<string | null>(null)
  // Iyimser tasima suruyorken sunucu verisiyle yerel siralamayi yeniden kurma
  const [pendingMoves, setPendingMoves] = useState(0)
  const mutating =
    useIsMutating({ mutationKey: ['moveCard'] }) + useIsMutating({ mutationKey: ['moveList'] })
  const dragOrigin = useRef<{ listId: number; index: number } | null>(null)

  const cardsById = useMemo(
    () => new Map<number, CardSummary>(board.data?.cards.map((c) => [c.id, c]) ?? []),
    [board.data],
  )
  const labels = useMemo(
    () => new Map<number, Label>(board.data?.labels.map((l) => [l.id, l]) ?? []),
    [board.data],
  )

  useEffect(() => {
    if (!board.data || activeKey || pendingMoves > 0 || mutating > 0) return // surukleme/tasima sirasinda sunucu verisiyle ezme
    const cols: Columns = {}
    board.data.lists.forEach((l) => (cols[l.id] = []))
    ;[...board.data.cards]
      .sort((a, b) => a.position - b.position)
      .forEach((c) => c.list_id != null && cols[c.list_id]?.push(c.id))
    setColumns(cols)
    setListOrder(board.data.lists.map((l) => l.id))
  }, [board.data, activeKey, pendingMoves, mutating])

  /** Tasima mutasyonunu baslatir; bitene kadar yerel siralama korunur. */
  function runMove<V>(mut: { mutate: (v: V, o: { onSettled: () => void }) => void }, vars: V) {
    setPendingMoves((n) => n + 1)
    mut.mutate(vars, { onSettled: () => setPendingMoves((n) => Math.max(0, n - 1)) })
  }

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }), // tik = karti ac
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  const containerOf = (key: string | number): number | null => {
    const { type, id } = parseKey(key)
    if (type === 'list') return id
    const entry = Object.entries(columns).find(([, ids]) => ids.includes(id))
    return entry ? Number(entry[0]) : null
  }

  function onDragStart(e: DragStartEvent) {
    setActiveKey(String(e.active.id))
    const { type, id } = parseKey(e.active.id)
    if (type === 'card') {
      const listId = containerOf(e.active.id)!
      dragOrigin.current = { listId, index: columns[listId].indexOf(id) }
    }
  }

  function onDragOver(e: DragOverEvent) {
    const { active, over } = e
    if (!over || parseKey(active.id).type !== 'card') return
    const from = containerOf(active.id)
    const to = containerOf(over.id)
    if (from == null || to == null || from === to) return
    // Kart baska listeye gecti: yerel durumda tasi
    setColumns((cols) => {
      const cardId = parseKey(active.id).id
      const target = cols[to]
      const overIsCard = parseKey(over.id).type === 'card'
      const index = overIsCard ? target.indexOf(parseKey(over.id).id) : target.length
      return {
        ...cols,
        [from]: cols[from].filter((id) => id !== cardId),
        [to]: [...target.slice(0, index), cardId, ...target.slice(index)],
      }
    })
  }

  function onDragEnd(e: DragEndEvent) {
    const { active, over } = e
    const { type, id } = parseKey(active.id)

    if (type === 'list') {
      if (over && active.id !== over.id) {
        const overList = containerOf(over.id)
        const oldIndex = listOrder.indexOf(id)
        const newIndex = overList != null ? listOrder.indexOf(overList) : oldIndex
        if (newIndex !== oldIndex) {
          setListOrder(arrayMove(listOrder, oldIndex, newIndex))
          runMove(m.moveList, { id, index: newIndex })
        }
      }
      setActiveKey(null)
      return
    }

    // kart
    const listId = containerOf(active.id)
    let finalCols = columns
    if (over && listId != null && parseKey(over.id).type === 'card') {
      const ids = columns[listId]
      const oldIndex = ids.indexOf(id)
      const newIndex = ids.indexOf(parseKey(over.id).id)
      if (newIndex !== -1 && oldIndex !== newIndex) {
        finalCols = { ...columns, [listId]: arrayMove(ids, oldIndex, newIndex) }
        setColumns(finalCols)
      }
    }
    const origin = dragOrigin.current
    if (listId != null && origin) {
      const index = finalCols[listId].indexOf(id)
      if (origin.listId !== listId || origin.index !== index) {
        runMove(m.moveCard, { id, list_id: listId, index })
      }
    }
    dragOrigin.current = null
    setActiveKey(null)
  }

  // --- board ayarlari ---
  const [editing, setEditing] = useState(false)
  const [newList, setNewList] = useState('')
  const [labelName, setLabelName] = useState('')
  const [labelColor, setLabelColor] = useState(COLORS[1])

  if (board.isLoading) return <p className="p-6 text-slate-500">Yükleniyor…</p>
  if (board.error || !board.data)
    return <p className="p-6 text-red-600">{board.error?.message ?? 'Board bulunamadı'}</p>

  const b = board.data.board
  const listsById = new Map(board.data.lists.map((l) => [l.id, l]))
  const activeCard = activeKey?.startsWith('card-') ? cardsById.get(parseKey(activeKey).id) : null

  const activeList = activeKey?.startsWith('list-') ? listsById.get(parseKey(activeKey).id) : null

  function addList(e: FormEvent) {
    e.preventDefault()
    if (!newList.trim()) return
    m.createList.mutate(newList.trim(), { onSuccess: () => setNewList('') })
  }

  function addLabel(e: FormEvent) {
    e.preventDefault()
    if (!labelName.trim()) return
    m.createLabel.mutate({ name: labelName.trim(), color: labelColor }, { onSuccess: () => setLabelName('') })
  }

  const boardModel = b.default_model_id
    ? (models.data?.models.find((x) => x.id === b.default_model_id)?.label ?? b.default_model_id.replace('ollama:', ''))
    : null

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="relative flex flex-wrap items-center gap-x-5 gap-y-2 border-b border-slate-200 bg-surface py-3 pr-4 pl-6">
        {/* Ajanda sekmesi: board'un rengi sayfanin kenarinda */}
        <span aria-hidden className="absolute inset-y-0 left-0 w-1.5" style={{ backgroundColor: b.color }} />
        <div className="min-w-0">
          <h1 className="text-[26px] leading-tight">{b.name}</h1>
          <p className="flex flex-wrap items-center gap-x-4 text-[13px] text-slate-600">
            {b.scope_description && <span className="max-w-xl truncate">{b.scope_description}</span>}
            {b.privacy === 'local_only' && (
              <span className="inline-flex items-center gap-1" title="Bu board'un verisi bulut modellere gönderilmez">
                <Lock size={12} aria-hidden /> Sadece local
              </span>
            )}
            {boardModel && (
              <span className="inline-flex items-center gap-1" title="Bu board açıkken asistan otomatik olarak bu modeli kullanır">
                <Sparkles size={12} aria-hidden /> {boardModel}
              </span>
            )}
          </p>
        </div>
        <div className="ml-auto flex items-center gap-3">
          <Segmented
            label="Görünüm"
            value={view}
            onChange={setView}
            options={[
              { value: 'kanban' as const, label: 'Kanban' },
              { value: 'graph' as const, label: 'İlişkiler' },
            ]}
          />
          <button onClick={() => setEditing(true)} className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:border-slate-900">
            <Settings2 size={15} aria-hidden /> Board ayarları
          </button>
        </div>
      </div>

      {b.system_kind === 'inbox' && (
        <InboxTriage openCount={board.data.cards.filter((c) => c.status !== 'completed' && !c.is_archived).length} />
      )}

      {view === 'graph' ? (
        <Suspense fallback={<p className="p-6 text-slate-500">İlişki görünümü yükleniyor…</p>}>
          <GraphView boardId={boardId} labels={labels} onOpenCard={openCard} />
        </Suspense>
      ) : (
      <DndContext
        sensors={sensors}
        collisionDetection={collisionDetection}
        measuring={{ droppable: { strategy: MeasuringStrategy.Always } }}
        autoScroll={{ threshold: { x: 0.15, y: 0.1 }, acceleration: 8 }}
        onDragStart={onDragStart}
        onDragOver={onDragOver}
        onDragEnd={onDragEnd}
        onDragCancel={() => {
          dragOrigin.current = null
          setActiveKey(null)
        }}
      >
        <div
          className="board-bg flex min-h-0 flex-1 items-start gap-3 overflow-x-auto p-4"
          data-bg={b.background ?? 'none'}
          style={{ '--board-color': b.color } as CSSProperties}
        >
          <SortableContext items={listOrder.map(listKey)} strategy={horizontalListSortingStrategy}>
            {listOrder.map((listId) => {
              const list = listsById.get(listId)
              if (!list) return null
              const cards = (columns[listId] ?? [])
                .map((id) => cardsById.get(id))
                .filter((c): c is CardSummary => !!c)
              return (
                <KanbanList
                  key={listId}
                  list={list}
                  cards={cards}
                  labels={labels}
                  onOpenCard={openCard}
                  onToggleCard={(c) => m.toggleCard.mutate({ id: c.id, done: c.status !== 'completed' })}
                  onAddCard={(list_id, title) => m.createCard.mutate({ list_id, title })}
                  onRename={(id, name) => m.updateList.mutate({ id, name })}
                  onToggleDone={(id, is_done_list) => m.updateList.mutate({ id, is_done_list })}
                  onDelete={(id) => m.deleteList.mutate(id)}
                />
              )
            })}
          </SortableContext>

          <form onSubmit={addList} className="w-72 shrink-0 rounded-xl bg-slate-100/60 p-2">
            <input
              className="w-full rounded-lg border border-transparent bg-transparent px-2 py-1.5 text-sm placeholder:text-slate-500 focus:border-slate-300 focus:bg-surface"
              placeholder="+ Liste ekle"
              value={newList}
              onChange={(e) => setNewList(e.target.value)}
            />
          </form>
        </div>

        <DragOverlay
          dropAnimation={
            reducedMotion()
              ? null
              : {
                  duration: 200,
                  easing: 'cubic-bezier(0.18,0.67,0.6,1.22)',
                  sideEffects: defaultDropAnimationSideEffects({ styles: { active: { opacity: '0.4' } } }),
                }
          }
        >
          {activeCard ? <CardFace card={activeCard} labels={labels} dragging /> : null}
          {activeList ? (
            <ListOverlay
              list={activeList}
              cards={(columns[activeList.id] ?? []).map((id) => cardsById.get(id)).filter((c): c is CardSummary => !!c)}
              labels={labels}
            />
          ) : null}
        </DragOverlay>
      </DndContext>
      )}

      {(m.moveCard.error || m.moveList.error || m.deleteList.error || m.createCard.error || m.toggleCard.error) && (
        <p className="px-4 pb-2 text-sm text-red-600">
          {m.toggleCard.error && !(m.moveCard.error || m.moveList.error || m.deleteList.error || m.createCard.error)
            ? `Kart güncellenemedi: ${m.toggleCard.error.message}`
            : (m.moveCard.error ?? m.moveList.error ?? m.deleteList.error ?? m.createCard.error)?.message}
        </p>
      )}

      {openCardId !== null && (
        <CardModal
          cardId={openCardId}
          board={board.data}
          onClose={closeCard}
          onOpenCard={openCard}
        />
      )}

      {editing && (
        <Modal title="Board'u düzenle" onClose={() => setEditing(false)}>
          <BoardForm
            initial={b}
            submitLabel="Kaydet"
            busy={updateBoard.isPending}
            onCancel={() => setEditing(false)}
            onSubmit={(data) => updateBoard.mutate(data, { onSuccess: () => setEditing(false) })}
          />

          <h3 className="mt-6 mb-2 text-sm font-medium">Etiketler</h3>
          <div className="mb-2 flex flex-wrap gap-1.5">
            {board.data.labels.map((l) => (
              <span key={l.id} className="rounded px-2 py-0.5 text-xs" style={{ backgroundColor: l.color, color: readableTextOn(l.color) }}>
                {l.name}
              </span>
            ))}
          </div>
          <form onSubmit={addLabel} className="flex items-center gap-2">
            <input
              className="flex-1 rounded-md border border-slate-300 px-2 py-1 text-sm"
              placeholder="Yeni etiket"
              maxLength={50}
              value={labelName}
              onChange={(e) => setLabelName(e.target.value)}
            />
            <select className="rounded-md border border-slate-300 px-1 py-1 text-sm" value={labelColor} onChange={(e) => setLabelColor(e.target.value)} style={{ color: labelColor }}>
              {COLORS.map((c) => (
                <option key={c} value={c} style={{ color: c }}>●</option>
              ))}
            </select>
            <button className="rounded-md bg-slate-200 px-3 py-1 text-sm">Ekle</button>
          </form>

          <div className="mt-6 flex justify-between border-t border-slate-200 pt-4 text-sm">
            <button
              className="text-slate-600 hover:underline"
              onClick={() => updateBoard.mutate({ is_archived: true }, { onSuccess: () => navigate('/') })}
            >
              Arşivle
            </button>
            {b.system_kind === 'inbox' ? (
              <span className="text-slate-500">Gelen Kutusu silinemez</span>
            ) : (
              <button
                className="text-red-600 hover:underline"
                onClick={() => {
                  if (confirm(`"${b.name}" board'u tüm kartlarıyla silinsin mi?`))
                    deleteBoard.mutate(b.id, { onSuccess: () => navigate('/') })
                }}
              >
                Board'u sil
              </button>
            )}
          </div>
        </Modal>
      )}
    </div>
  )
}
