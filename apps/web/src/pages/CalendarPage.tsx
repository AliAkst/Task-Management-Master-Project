import { useEffect, useMemo, useRef, useState } from 'react'
import { useQueries, useQuery } from '@tanstack/react-query'
import FullCalendar from '@fullcalendar/react'
import dayGridPlugin from '@fullcalendar/daygrid'
import timeGridPlugin from '@fullcalendar/timegrid'
import interactionPlugin, { Draggable } from '@fullcalendar/interaction'
import trLocale from '@fullcalendar/core/locales/tr'
import type {
  DatesSetArg,
  DateSelectArg,
  EventChangeArg,
  EventClickArg,
  EventInput,
} from '@fullcalendar/core'
import type { DropArg } from '@fullcalendar/interaction'
import { useBoard, useBoards, keys as boardKeys } from '../api/boards'
import { useCalendar, useCalendarMutations } from '../api/calendar'
import CardModal from '../components/CardModal'
import EventDialog, { type EventDraft } from '../components/EventDialog'
import { api } from '../lib/api'
import type { BoardDetail, CalendarItem, CardSummary, UserSettings } from '../lib/types'

const HOUR = 60 * 60 * 1000
const addMs = (d: Date, ms: number) => new Date(d.getTime() + ms)

/** Takvimden acilan kart: kartin board verisini yukleyip CardModal'i gosterir. */
function CalendarCardModal({ boardId, cardId, onClose, onOpenCard }: {
  boardId: number
  cardId: number
  onClose: () => void
  onOpenCard: (id: number) => void
}) {
  const board = useBoard(boardId)
  if (!board.data) return null
  return <CardModal cardId={cardId} board={board.data} onClose={onClose} onOpenCard={onOpenCard} />
}

export default function CalendarPage() {
  const boards = useBoards()
  const settings = useQuery({ queryKey: ['settings'], queryFn: () => api<UserSettings>('/settings/') })
  const m = useCalendarMutations()

  const [range, setRange] = useState<{ start: string; end: string } | null>(null)
  const [hidden, setHidden] = useState<Set<number>>(new Set())
  const [draft, setDraft] = useState<EventDraft | null>(null)
  const [openCard, setOpenCard] = useState<{ cardId: number; boardId: number } | null>(null)

  const allBoards = boards.data ?? []
  const shownIds = allBoards.filter((b) => !hidden.has(b.id)).map((b) => b.id)
  // Hepsi aciksa filtre gonderme (board'suz etkinlikler de gorunsun)
  const filter = hidden.size === 0 ? [] : shownIds
  const calendar = useCalendar(range?.start ?? null, range?.end ?? null, filter)
  const boardById = useMemo(() => new Map(allBoards.map((b) => [b.id, b])), [allBoards])

  // --- sol panel: tum board'lardaki acik kartlar ---
  const details = useQueries({
    queries: allBoards.map((b) => ({
      queryKey: boardKeys.board(b.id),
      queryFn: () => api<BoardDetail>(`/boards/${b.id}`),
    })),
  })
  const scheduledInView = new Set(
    (calendar.data ?? []).filter((i) => i.kind === 'event').map((i) => i.card_id),
  )
  const openCards: CardSummary[] = details
    .flatMap((q) => q.data?.cards ?? [])
    .filter((c) => c.status !== 'completed' && !hidden.has(c.board_id ?? -1))
    // Ana kart parcalara bolunduyse parcalari planlanir, ana kart degil
    .filter((c) => c.subtask_total === 0)
    .sort((a, b) => Number(a.blocked) - Number(b.blocked))

  // Sol paneldeki kartlari takvime surukelenebilir yap
  const listRef = useRef<HTMLUListElement>(null)
  useEffect(() => {
    if (!listRef.current) return
    const d = new Draggable(listRef.current, {
      itemSelector: '[data-card-id]',
      eventData: (el) => ({
        title: el.dataset.title,
        duration: { minutes: Number(el.dataset.minutes) },
        create: false, // olusturmayi biz yapiyoruz (sunucuya kaydedip)
      }),
    })
    return () => d.destroy()
  }, [])

  const events: EventInput[] = (calendar.data ?? []).map((i: CalendarItem) => {
    const done = i.card_status === 'completed'
    const deadline = i.kind === 'deadline'
    return {
      id: i.id,
      title: `${deadline ? '⏰ ' : ''}${i.title}`,
      start: i.start,
      end: i.end ?? undefined,
      allDay: i.all_day,
      backgroundColor: deadline ? '#fff' : i.color,
      borderColor: i.color,
      textColor: deadline ? i.color : '#fff',
      durationEditable: !deadline,
      classNames: done ? ['opacity-50', 'line-through'] : [],
      extendedProps: { item: i },
    }
  })

  function onDatesSet(arg: DatesSetArg) {
    setRange({ start: arg.start.toISOString(), end: arg.end.toISOString() })
  }

  function onSelect(arg: DateSelectArg) {
    arg.view.calendar.unselect()
    setDraft({
      title: '',
      start: arg.start.toISOString(),
      end: arg.end.toISOString(),
      allDay: arg.allDay,
      boardId: null,
      cardId: null,
    })
  }

  function onDrop(arg: DropArg) {
    const el = arg.draggedEl
    const minutes = Number(el.dataset.minutes)
    const start = arg.date
    const end = arg.allDay ? addMs(start, 24 * HOUR) : addMs(start, minutes * 60 * 1000)
    m.create.mutate({
      card_id: Number(el.dataset.cardId),
      start_at: start.toISOString(),
      end_at: end.toISOString(),
      all_day: arg.allDay,
    })
  }

  function onChange(arg: EventChangeArg) {
    const item = arg.event.extendedProps.item as CalendarItem
    const start = arg.event.start!
    if (item.kind === 'deadline') {
      // Son tarih: yeni gunun yerel 23:59'u
      const due = new Date(start)
      due.setHours(23, 59, 0, 0)
      m.setDueDate.mutate({ cardId: item.card_id!, due: due.toISOString() }, { onError: arg.revert })
      return
    }
    const allDay = arg.event.allDay
    const end = arg.event.end ?? addMs(start, allDay ? 24 * HOUR : HOUR)
    m.update.mutate(
      { id: item.event_id!, start_at: start.toISOString(), end_at: end.toISOString(), all_day: allDay },
      { onError: arg.revert },
    )
  }

  function onClick(arg: EventClickArg) {
    const item = arg.event.extendedProps.item as CalendarItem
    if (item.kind === 'deadline') {
      setOpenCard({ cardId: item.card_id!, boardId: item.board_id! })
      return
    }
    setDraft({
      id: item.event_id!,
      title: item.title,
      start: item.start,
      end: item.end!,
      allDay: item.all_day,
      boardId: item.board_id,
      cardId: item.card_id,
      location: item.location,
    })
  }

  function toggleBoard(id: number) {
    setHidden((h) => {
      const next = new Set(h)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const weekStart = settings.data?.week_start ?? 0 // 0=Pazartesi
  const error = (m.create.error ?? m.update.error ?? m.setDueDate.error)?.message

  return (
    <div className="flex min-h-0 flex-1">
      <aside className="flex w-64 shrink-0 flex-col gap-4 overflow-y-auto border-r border-slate-200 bg-white p-3">
        <section>
          <h2 className="mb-2 text-xs font-medium tracking-wide text-slate-500 uppercase">Board'lar</h2>
          <div className="flex flex-wrap gap-1.5">
            {allBoards.map((b) => {
              const on = !hidden.has(b.id)
              return (
                <button
                  key={b.id}
                  onClick={() => toggleBoard(b.id)}
                  className={`rounded-full px-2.5 py-1 text-xs ${on ? 'text-white' : 'text-slate-500 ring-1 ring-slate-300'}`}
                  style={on ? { backgroundColor: b.color } : undefined}
                >
                  {b.name}
                </button>
              )
            })}
          </div>
        </section>

        <section className="min-h-0 flex-1">
          <h2 className="mb-1 text-xs font-medium tracking-wide text-slate-500 uppercase">Açık kartlar</h2>
          <p className="mb-2 text-xs text-slate-400">Takvime sürükleyerek zaman ayır.</p>
          <ul ref={listRef} className="space-y-1.5">
            {openCards.map((c) => {
              const board = boardById.get(c.board_id ?? -1)
              return (
                <li
                  key={c.id}
                  data-card-id={c.id}
                  data-title={c.title}
                  data-minutes={c.estimated_minutes || 60}
                  className="cursor-grab rounded-md border-l-4 bg-slate-50 px-2 py-1.5 text-xs hover:bg-slate-100"
                  style={{ borderLeftColor: board?.color }}
                  title={c.blocked ? 'Ön koşulları bitmedi' : undefined}
                >
                  <div className={c.blocked ? 'text-slate-400' : ''}>
                    {c.blocked && '⛓ '}
                    {c.title}
                  </div>
                  <div className="mt-0.5 flex gap-2 text-[10px] text-slate-400">
                    <span>{board?.name}</span>
                    <span>{c.estimated_minutes ? `${c.estimated_minutes} dk` : '~60 dk'}</span>
                    {scheduledInView.has(c.id) && <span className="text-green-600">✓ bu aralıkta planlı</span>}
                  </div>
                </li>
              )
            })}
            {openCards.length === 0 && <li className="text-xs text-slate-400">Açık kart yok.</li>}
          </ul>
        </section>
      </aside>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col p-3">
        {error && <p className="mb-2 text-sm text-red-600">{error}</p>}
        <div className="min-h-0 flex-1 rounded-xl bg-white p-2 shadow-sm ring-1 ring-slate-200">
          <FullCalendar
            plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
            locale={trLocale}
            initialView="timeGridWeek"
            headerToolbar={{ left: 'prev,next today', center: 'title', right: 'dayGridMonth,timeGridWeek,timeGridDay' }}
            firstDay={(weekStart + 1) % 7}
            height="100%"
            nowIndicator
            scrollTime="07:00:00"
            editable
            selectable
            selectMirror
            droppable
            events={events}
            datesSet={onDatesSet}
            select={onSelect}
            drop={onDrop}
            eventChange={onChange}
            eventClick={onClick}
            dayMaxEvents
          />
        </div>
      </div>

      {draft && (
        <EventDialog
          draft={draft}
          boards={allBoards}
          onClose={() => setDraft(null)}
          onOpenCard={(cardId) => {
            const item = calendar.data?.find((i) => i.card_id === cardId)
            setDraft(null)
            if (item?.board_id) setOpenCard({ cardId, boardId: item.board_id })
          }}
        />
      )}
      {openCard && (
        <CalendarCardModal
          boardId={openCard.boardId}
          cardId={openCard.cardId}
          onClose={() => setOpenCard(null)}
          onOpenCard={(cardId) => setOpenCard({ ...openCard, cardId })}
        />
      )}
    </div>
  )
}
