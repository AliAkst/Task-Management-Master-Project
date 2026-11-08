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
import { Check, Hourglass, Loader2, RefreshCw, Video } from 'lucide-react'
import { useIntegrationMutations, useMicrosoftCalendarEnabled } from '../api/integrations'
import { api } from '../lib/api'
import type { BoardDetail, CalendarEvent, CalendarItem, CardSummary, UserSettings } from '../lib/types'

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
  const msCalendarOn = useMicrosoftCalendarEnabled()
  const { syncMicrosoftCalendar } = useIntegrationMutations()

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
      title: deadline ? `Son gün: ${i.title}` : i.title,
      start: i.start,
      end: i.end ?? undefined,
      allDay: i.all_day,
      backgroundColor: deadline ? '#fff' : i.color,
      borderColor: i.color,
      textColor: deadline ? i.color : '#fff',
      durationEditable: !deadline && !i.recurrence_rule && !i.external,
      // Tekrarlar suruklenmez: degisiklik butun seriye uygulanir (pencereden)
      startEditable: !i.recurrence_rule && !i.external,
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

  async function onClick(arg: EventClickArg) {
    const item = arg.event.extendedProps.item as CalendarItem
    if (item.kind === 'deadline') {
      setOpenCard({ cardId: item.card_id!, boardId: item.board_id! })
      return
    }
    if (item.recurrence_rule || item.external) {
      // Tekrar degil seri duzenlenir (dis etkinlikte not da gerekir): serinin asil zamanini getir
      const ev = await api<CalendarEvent>(`/events/${item.event_id}`)
      setDraft({
        id: ev.id,
        title: ev.title,
        start: ev.start_at,
        end: ev.end_at,
        allDay: ev.all_day,
        boardId: ev.board_id,
        cardId: ev.card_id,
        location: ev.location,
        notes: ev.notes,
        recurrenceRule: ev.recurrence_rule,
        meetingUrl: ev.meeting_url,
        external: ev.external,
      })
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
      <aside className="flex w-72 shrink-0 flex-col gap-5 overflow-y-auto border-r border-slate-200 bg-white p-4">
        <section>
          <h2 className="mb-2 text-[17px]">Gösterilen alanlar</h2>
          <div className="flex flex-wrap gap-1.5">
            {allBoards.map((b) => {
              const on = !hidden.has(b.id)
              return (
                <button
                  key={b.id}
                  onClick={() => toggleBoard(b.id)}
                  aria-pressed={on}
                  className={`rounded-full px-3 py-1 text-[13px] font-semibold ${on ? 'text-white' : 'text-slate-500 line-through ring-1 ring-slate-300'}`}
                  style={on ? { backgroundColor: b.color } : undefined}
                >
                  {b.name}
                </button>
              )
            })}
          </div>
        </section>

        <section className="min-h-0 flex-1">
          <h2 className="mb-1 text-[17px]">Açık kartlar</h2>
          <p className="mb-3 text-[14px] text-slate-600">Bir kartı takvime sürükleyerek ona zaman ayır.</p>
          <ul ref={listRef} className="space-y-1.5">
            {openCards.map((c) => {
              const board = boardById.get(c.board_id ?? -1)
              return (
                <li
                  key={c.id}
                  data-card-id={c.id}
                  data-title={c.title}
                  data-minutes={c.estimated_minutes || 60}
                  className="cursor-grab rounded-md border border-l-4 border-slate-200 bg-white px-2.5 py-2 text-[14px] hover:border-slate-400 active:cursor-grabbing"
                  style={{ borderLeftColor: board?.color }}
                  title={c.blocked ? 'Ön koşulları bitmedi' : undefined}
                >
                  <div className={`leading-snug ${c.blocked ? 'text-slate-500' : 'text-slate-900'}`}>{c.title}</div>
                  <div className="mt-1 flex flex-wrap items-center gap-x-2.5 text-[12px] text-slate-500">
                    <span>{board?.name}</span>
                    <span className="tabular-nums">{c.estimated_minutes ? `${c.estimated_minutes} dk` : 'süre yok, 60 dk'}</span>
                    {c.blocked && <span className="inline-flex items-center gap-0.5 text-amber-800"><Hourglass size={12} aria-hidden />Bekliyor</span>}
                    {scheduledInView.has(c.id) && <span className="inline-flex items-center gap-0.5 text-green-700"><Check size={12} aria-hidden />Bu aralıkta planlı</span>}
                  </div>
                </li>
              )
            })}
            {openCards.length === 0 && <li className="text-[14px] text-slate-500">Planlanacak açık kart yok.</li>}
          </ul>
        </section>
      </aside>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col p-4">
        {error && <p className="mb-2 text-sm text-red-700">{error}</p>}
        {msCalendarOn && (
          <div className="mb-2 flex flex-wrap items-center justify-end gap-3 text-[14px]">
            {syncMicrosoftCalendar.error && <span className="text-red-700">{syncMicrosoftCalendar.error.message}</span>}
            {syncMicrosoftCalendar.data && !syncMicrosoftCalendar.error && (
              <span className={syncMicrosoftCalendar.data.errors.length ? 'text-red-700' : 'text-slate-600'} aria-live="polite">
                {syncMicrosoftCalendar.data.errors.length
                  ? syncMicrosoftCalendar.data.errors.join('; ')
                  : `${syncMicrosoftCalendar.data.created} yeni, ${syncMicrosoftCalendar.data.updated} güncellendi, ${syncMicrosoftCalendar.data.removed} silindi`}
              </span>
            )}
            <button
              disabled={syncMicrosoftCalendar.isPending}
              onClick={() => syncMicrosoftCalendar.mutate()}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 px-3 py-1 hover:bg-slate-100 disabled:opacity-40"
            >
              {syncMicrosoftCalendar.isPending ? (
                <Loader2 size={14} className="animate-spin" aria-hidden />
              ) : (
                <RefreshCw size={14} aria-hidden />
              )}
              Toplantıları çek
            </button>
          </div>
        )}
        <div className="min-h-0 flex-1 rounded-lg border border-slate-200 bg-white p-3">
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
            eventContent={(arg) => {
              const item = arg.event.extendedProps.item as CalendarItem
              if (!item.meeting_url) return true // varsayilan gorunum
              return (
                <div className="fc-event-main-frame">
                  {arg.timeText && <div className="fc-event-time">{arg.timeText}</div>}
                  <div className="fc-event-title-container">
                    <div className="fc-event-title fc-sticky">
                      <Video size={12} className="mr-1 inline-block align-[-1px]" aria-label="Çevrimiçi toplantı" />
                      {arg.event.title}
                    </div>
                  </div>
                </div>
              )
            }}
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
