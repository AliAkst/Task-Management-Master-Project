import { useState, type FormEvent } from 'react'
import { Video } from 'lucide-react'
import { useCalendarMutations } from '../api/calendar'
import { formatRange, fromLocalInput, toLocalInput } from '../lib/format'
import type { BoardWithCounts } from '../lib/types'
import Modal from './Modal'
import RecurrencePicker from './RecurrencePicker'
import { dayCodeOf } from '../lib/rrule'

export interface EventDraft {
  id?: number // varsa duzenleme
  title: string
  start: string // ISO
  end: string // ISO
  allDay: boolean
  boardId: number | null
  cardId: number | null
  location?: string | null
  notes?: string | null
  recurrenceRule?: string | null
  // Cevrimici toplanti katilim baglantisi (Teams)
  meetingUrl?: string | null
  // Dis takvimden gelen etkinlik: salt okunur gosterilir
  external?: { provider: string; url?: string | null } | null
}

interface Props {
  draft: EventDraft
  boards: BoardWithCounts[]
  onClose: () => void
  onOpenCard?: (cardId: number) => void
}

const dateOnly = (iso: string) => toLocalInput(iso).slice(0, 10)
/** Tum gun: yerel gece yarisi; bitis haric (exclusive) -> ertesi gun 00:00. */
const dayStart = (d: string) => new Date(`${d}T00:00`).toISOString()
const dayEndExclusive = (d: string) => {
  const x = new Date(`${d}T00:00`)
  x.setDate(x.getDate() + 1)
  return x.toISOString()
}

function EventForm({ draft, boards, onClose, onOpenCard }: Props) {
  const m = useCalendarMutations()
  const editing = draft.id !== undefined
  const linked = draft.cardId !== null

  const [title, setTitle] = useState(draft.title)
  const [allDay, setAllDay] = useState(draft.allDay)
  const [start, setStart] = useState(toLocalInput(draft.start))
  const [end, setEnd] = useState(toLocalInput(draft.end))
  // Tum gunde bitis gunu dahil gosterilir (kullanici icin dogal olan)
  const [startDay, setStartDay] = useState(dateOnly(draft.start))
  const [endDay, setEndDay] = useState(() => {
    if (!draft.allDay) return dateOnly(draft.end)
    const d = new Date(draft.end)
    d.setDate(d.getDate() - 1)
    return dateOnly(d.toISOString())
  })
  const [boardId, setBoardId] = useState(draft.boardId)
  const [location, setLocation] = useState(draft.location ?? '')
  const [notes, setNotes] = useState(draft.notes ?? '')
  const [rule, setRule] = useState<string | null>(draft.recurrenceRule ?? null)

  const error = (m.create.error ?? m.update.error ?? m.remove.error)?.message

  function submit(e: FormEvent) {
    e.preventDefault()
    const range = allDay
      ? { start_at: dayStart(startDay), end_at: dayEndExclusive(endDay < startDay ? startDay : endDay) }
      : { start_at: fromLocalInput(start), end_at: fromLocalInput(end) }
    const common = {
      title: title.trim() || undefined,
      all_day: allDay,
      location: location.trim() || null,
      notes: notes.trim() || null,
      recurrence_rule: rule,
      ...range,
    }
    if (editing) {
      m.update.mutate(
        { id: draft.id!, ...common, ...(linked ? {} : { board_id: boardId }) },
        { onSuccess: onClose },
      )
    } else {
      m.create.mutate(
        { ...common, board_id: linked ? null : boardId, card_id: draft.cardId },
        { onSuccess: onClose },
      )
    }
  }

  return (
    <Modal title={editing ? (linked ? 'Zaman bloğu' : 'Etkinlik') : 'Yeni etkinlik'} onClose={onClose}>
      <form onSubmit={submit} className="space-y-3 text-sm">
        <input
          autoFocus
          maxLength={200}
          required={!linked}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-base"
          placeholder={linked ? 'Başlık (boşsa kart başlığı)' : 'Başlık'}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />

        <label className="flex items-center gap-2">
          <input type="checkbox" checked={allDay} onChange={(e) => setAllDay(e.target.checked)} />
          Tüm gün
        </label>

        {allDay ? (
          <div className="grid grid-cols-2 gap-3">
            <label className="space-y-1">
              <span className="text-xs text-slate-500">Başlangıç</span>
              <input type="date" required className="w-full rounded-md border border-slate-300 px-2 py-1" value={startDay} onChange={(e) => setStartDay(e.target.value)} />
            </label>
            <label className="space-y-1">
              <span className="text-xs text-slate-500">Bitiş</span>
              <input type="date" required className="w-full rounded-md border border-slate-300 px-2 py-1" value={endDay} onChange={(e) => setEndDay(e.target.value)} />
            </label>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            <label className="space-y-1">
              <span className="text-xs text-slate-500">Başlangıç</span>
              <input type="datetime-local" required className="w-full rounded-md border border-slate-300 px-2 py-1" value={start} onChange={(e) => setStart(e.target.value)} />
            </label>
            <label className="space-y-1">
              <span className="text-xs text-slate-500">Bitiş</span>
              <input type="datetime-local" required className="w-full rounded-md border border-slate-300 px-2 py-1" value={end} onChange={(e) => setEnd(e.target.value)} />
            </label>
          </div>
        )}

        <RecurrencePicker
          value={rule}
          onChange={setRule}
          startDay={dayCodeOf(new Date(allDay ? `${startDay}T12:00` : start))}
          inputClass="w-full rounded-md border border-slate-300 px-2 py-1"
        />
        {editing && draft.recurrenceRule && (
          <p className="text-xs text-slate-500">
            Değişiklikler serinin tümüne uygulanır; tarih alanları serinin ilk tekrarını gösterir.
          </p>
        )}

        {linked ? (
          <p className="text-xs text-slate-500">
            Bir karta ayrılmış zaman bloğu; board'u kartın board'udur.{' '}
            {onOpenCard && (
              <button type="button" className="text-blue-600 hover:underline" onClick={() => onOpenCard(draft.cardId!)}>
                Kartı aç →
              </button>
            )}
          </p>
        ) : (
          <label className="block space-y-1">
            <span className="text-xs text-slate-500">Board</span>
            <select
              className="w-full rounded-md border border-slate-300 px-2 py-1"
              value={boardId ?? ''}
              onChange={(e) => setBoardId(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">— Board'suz —</option>
              {boards.map((b) => (
                <option key={b.id} value={b.id}>{b.name}</option>
              ))}
            </select>
          </label>
        )}

        <input
          maxLength={200}
          className="w-full rounded-md border border-slate-300 px-3 py-1.5"
          placeholder="Konum"
          value={location}
          onChange={(e) => setLocation(e.target.value)}
        />
        <textarea
          rows={2}
          className="w-full rounded-md border border-slate-300 px-3 py-1.5"
          placeholder="Not"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />

        {error && <p className="text-red-600">{error}</p>}

        <div className="flex items-center justify-between pt-2">
          {editing ? (
            <button
              type="button"
              className="text-red-600 hover:underline"
              onClick={() => m.remove.mutate(draft.id!, { onSuccess: onClose })}
            >
              {draft.recurrenceRule ? 'Seriyi sil' : linked ? 'Takvimden çıkar' : 'Sil'}
            </button>
          ) : (
            <span />
          )}
          <div className="flex gap-2">
            <button type="button" onClick={onClose} className="px-3 py-1.5 text-slate-600">Vazgeç</button>
            <button
              disabled={m.create.isPending || m.update.isPending}
              className="rounded-md bg-slate-900 px-4 py-1.5 font-medium text-on-ink disabled:opacity-50"
            >
              Kaydet
            </button>
          </div>
        </div>
      </form>
    </Modal>
  )
}

const PROVIDER_NAME: Record<string, { name: string; from: string; at: string }> = {
  google: { name: 'Google Takvim', from: 'Google Takvim’den', at: 'Google Takvim’de' },
  microsoft: { name: 'Outlook', from: 'Outlook’tan', at: 'Outlook’ta' },
}

/** Yalniz https baglantilari tiklanabilir (javascript: vb. engellenir). */
export const safeHttpsUrl = (url: string | null | undefined) => (url && /^https:\/\//i.test(url) ? url : null)

/** Dis takvimden gelen etkinlik: duzenlenemez, kaynakta acilir. */
function ExternalEventView({ draft, onClose }: Pick<Props, 'draft' | 'onClose'>) {
  const names = PROVIDER_NAME[draft.external!.provider] ?? {
    name: draft.external!.provider,
    from: draft.external!.provider,
    at: draft.external!.provider,
  }
  const joinUrl = safeHttpsUrl(draft.meetingUrl)
  const openUrl = safeHttpsUrl(draft.external!.url)
  return (
    <Modal title={`Etkinlik · ${names.name}`} onClose={onClose}>
      <div className="space-y-3 text-sm">
        <h3 className="text-lg font-semibold">{draft.title}</h3>
        <p>{formatRange(draft.start, draft.end, draft.allDay)}</p>
        {draft.location && <p className="text-slate-600">{draft.location}</p>}
        {draft.notes && <p className="max-h-48 overflow-auto whitespace-pre-wrap text-slate-600">{draft.notes}</p>}
        <p className="text-xs text-slate-500">
          Bu etkinlik {names.from} geliyor ve burada değiştirilemez; orada düzenle, sonraki senkronda güncellenir.
        </p>
        {joinUrl && (
          <a
            href={joinUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 rounded-md bg-slate-900 px-4 py-2 font-medium text-on-ink hover:bg-slate-700"
          >
            <Video size={16} aria-hidden /> Teams’te katıl
          </a>
        )}
        <div className="flex items-center justify-between pt-2">
          {openUrl ? (
            <a href={openUrl} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline">
              {names.at} aç →
            </a>
          ) : (
            <span />
          )}
          <button type="button" onClick={onClose} className="rounded-md border border-slate-300 px-4 py-1.5 font-medium hover:bg-slate-100">
            Kapat
          </button>
        </div>
      </div>
    </Modal>
  )
}

export default function EventDialog(props: Props) {
  return props.draft.external ? <ExternalEventView draft={props.draft} onClose={props.onClose} /> : <EventForm {...props} />
}
