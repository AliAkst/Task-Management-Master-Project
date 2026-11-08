import { useEffect, useRef, useState, type DragEvent, type FormEvent, type MouseEvent } from 'react'
import { Check, Circle, CornerLeftUp, ExternalLink, Hourglass, X } from 'lucide-react'
import { useUploads } from '../api/attachments'
import { useCard, useCardActivity, useCardMutations } from '../api/boards'
import {
  ACTION_LABEL,
  formatDateTime,
  fromDateInput,
  PRIORITY_LABEL,
  toDateInput,
} from '../lib/format'
import type { BoardDetail, TaskPriority } from '../lib/types'
import AttachmentsSection from './AttachmentsSection'
import CardSchedule from './CardSchedule'
import CardTime, { CardTimerButton } from './CardTime'
import MarkdownEditor from './MarkdownEditor'
import MarkdownView from './MarkdownView'
import Modal from './Modal'
import RecurrencePicker from './RecurrencePicker'
import { dayCodeOf } from '../lib/rrule'

interface Props {
  cardId: number
  board: BoardDetail
  onClose: () => void
  onOpenCard: (id: number) => void
}

const EXTERNAL_LABEL: Record<string, string> = {
  microsoft: 'Microsoft To Do',
  trello: 'Trello',
  google: 'Google',
}
const NOTE_ACTION: Record<string, string> = { created: 'eklendi', updated: 'düzenlendi', deleted: 'silindi' }
const section = 'mt-7'
const sectionTitle = 'mb-2 text-[15px] font-semibold text-slate-900'
const fieldLabel = 'block text-[13px] text-slate-600'
const input = 'w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-[14px]'

/** Alt kart / on kosul durumu: ikon + erisilebilir ad (renk tek basina anlam tasimaz). */
function StatusMark({ status, blocked }: { status: string; blocked?: boolean }) {
  if (status === 'completed') return <Check size={15} className="shrink-0 text-green-700" aria-label="Tamamlandı" />
  if (blocked) return <Hourglass size={14} className="shrink-0 text-amber-700" aria-label="Bekliyor" />
  return <Circle size={14} className="shrink-0 text-slate-400" aria-label="Açık" />
}

export default function CardModal({ cardId, board, onClose, onOpenCard }: Props) {
  const card = useCard(cardId)
  const activity = useCardActivity(cardId)
  const m = useCardMutations(cardId, board.board.id)
  const uploads = useUploads(cardId, board.board.id)
  const [dropping, setDropping] = useState(false)
  const dragDepth = useRef(0)

  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [editingDesc, setEditingDesc] = useState(false)
  const [note, setNote] = useState('')
  const [editingNote, setEditingNote] = useState<number | null>(null)
  const [noteDraft, setNoteDraft] = useState('')
  const [item, setItem] = useState('')
  const [showHistory, setShowHistory] = useState(false)
  const [subtask, setSubtask] = useState('')
  const [splitOpen, setSplitOpen] = useState(false)
  const [splitParts, setSplitParts] = useState('3')
  const [splitHours, setSplitHours] = useState('')
  const [splitChain, setSplitChain] = useState(true)
  const [depChoice, setDepChoice] = useState('')

  useEffect(() => {
    if (!card.data) return
    setTitle(card.data.title)
    setDescription(card.data.description ?? '')
  }, [card.data])

  if (card.error) {
    return (
      <Modal onClose={onClose}>
        <p className="text-red-600">{card.error.message}</p>
      </Modal>
    )
  }
  if (!card.data) {
    return (
      <Modal onClose={onClose}>
        <p className="text-slate-500">Yükleniyor…</p>
      </Modal>
    )
  }

  const c = card.data
  const done = c.status === 'completed'
  const list = board.lists.find((l) => l.id === c.list_id)

  const hasFiles = (e: DragEvent) => Array.from(e.dataTransfer.types).includes('Files')
  const dragProps = {
    onDragEnter: (e: DragEvent) => {
      if (!hasFiles(e)) return
      dragDepth.current += 1
      setDropping(true)
    },
    onDragOver: (e: DragEvent) => {
      if (hasFiles(e)) e.preventDefault()
    },
    onDragLeave: (e: DragEvent) => {
      if (!hasFiles(e)) return
      dragDepth.current = Math.max(0, dragDepth.current - 1)
      if (dragDepth.current === 0) setDropping(false)
    },
    onDrop: (e: DragEvent) => {
      if (!hasFiles(e)) return
      e.preventDefault()
      dragDepth.current = 0
      setDropping(false)
      void uploads.upload(Array.from(e.dataTransfer.files))
    },
  }

  const saveTitle = () => {
    if (title.trim() && title.trim() !== c.title) m.update.mutate({ title: title.trim() })
    else setTitle(c.title)
  }
  const saveDescription = () => {
    setEditingDesc(false)
    if (description !== (c.description ?? '')) m.update.mutate({ description: description || null })
  }
  const toggleLabel = (id: number) => {
    const next = c.label_ids.includes(id) ? c.label_ids.filter((x) => x !== id) : [...c.label_ids, id]
    m.update.mutate({ label_ids: next })
  }
  const addNote = () => {
    if (note.trim()) m.addNote.mutate(note.trim(), { onSuccess: () => setNote('') })
  }
  const startEditNote = (id: number, content: string) => {
    setEditingNote(id)
    setNoteDraft(content)
  }
  const saveNote = (id: number, original: string) => {
    const text = noteDraft.trim()
    if (!text || text === original.trim()) return setEditingNote(null)
    m.updateNote.mutate({ id, content: text }, { onSuccess: () => setEditingNote(null) })
  }
  const cancelNote = (original: string) => {
    if (noteDraft !== original && !confirm('Değişiklikler kaybolsun mu?')) return
    setEditingNote(null)
  }
  const cancelDescription = () => {
    if (description !== (c.description ?? '') && !confirm('Değişiklikler kaybolsun mu?')) return
    setDescription(c.description ?? '')
    setEditingDesc(false)
  }
  const onNoteDoubleClick = (e: MouseEvent, id: number, content: string) => {
    if ((e.target as HTMLElement).closest('a,button')) return
    startEditNote(id, content)
  }
  const addSubtask = (e: FormEvent) => {
    e.preventDefault()
    if (subtask.trim()) m.addSubtask.mutate(subtask.trim(), { onSuccess: () => setSubtask('') })
  }
  const submitSplit = (e: FormEvent) => {
    e.preventDefault()
    const hours = parseFloat(splitHours.replace(',', '.'))
    m.split.mutate(
      {
        parts: Number(splitParts),
        total_minutes: Number.isFinite(hours) ? Math.round(hours * 60) : null,
        chain: splitChain,
      },
      { onSuccess: () => setSplitOpen(false) },
    )
  }
  const depCandidates = board.cards.filter(
    (x) => x.id !== c.id && !c.depends_on.some((d) => d.id === x.id) && x.status !== 'completed',
  )
  const hours = (min: number) => Math.round(min / 6) / 10
  const addItem = (e: FormEvent) => {
    e.preventDefault()
    if (item.trim()) m.addItem.mutate(item.trim(), { onSuccess: () => setItem('') })
  }

  const meta = [
    list ? `“${list.name}” listesinde` : 'Listesiz',
    c.created_by === 'ai' ? 'asistan oluşturdu' : null,
    c.completed_at ? `${formatDateTime(c.completed_at)} tarihinde tamamlandı` : null,
  ].filter(Boolean)

  return (
    <Modal size="xl" onClose={onClose} label={c.title}>
      <div {...dragProps} className={`relative rounded-md ${dropping ? "outline-2 outline-dashed outline-blue-600 outline-offset-4" : ""}`}>
        {dropping && (
          <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center rounded-md bg-blue-50/80 text-[16px] font-semibold text-blue-800">
            Bırak, karta eklensin
          </div>
        )}
      {/* Baslik */}
      <div className="flex items-start gap-3 border-b border-slate-200 pb-4">
        <button
          title={done ? 'Yeniden aç' : 'Tamamla'}
          aria-label={done ? 'Yeniden aç' : 'Tamamla'}
          onClick={() => m.update.mutate({ status: done ? 'pending' : 'completed' })}
          className={`mt-1.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2 ${
            done ? 'border-green-700 bg-green-700 text-white' : 'border-slate-300 hover:border-green-700'
          }`}
        >
          {done && <Check size={14} strokeWidth={3} aria-hidden />}
        </button>
        <div className="min-w-0 flex-1">
          <input
            className="font-display w-full rounded px-1 text-[26px] leading-tight font-[650] focus:outline-slate-300"
            value={title}
            maxLength={200}
            aria-label="Kart başlığı"
            onChange={(e) => setTitle(e.target.value)}
            onBlur={saveTitle}
            onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
          />
          <p className="flex flex-wrap items-center gap-x-3 px-1 text-[13px] text-slate-600">
            {c.parent && (
              <button className="inline-flex items-center gap-1 text-blue-700 hover:underline" onClick={() => onOpenCard(c.parent!.id)}>
                <CornerLeftUp size={13} aria-hidden /> {c.parent.title}
              </button>
            )}
            <span>{meta.join(', ')}</span>
            {c.external && (
              <span className="inline-flex items-center gap-1">
                {c.external.url ? (
                  <a href={c.external.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 underline">
                    {EXTERNAL_LABEL[c.external.provider] ?? c.external.provider}’dan <ExternalLink size={11} aria-hidden />
                  </a>
                ) : (
                  <>{EXTERNAL_LABEL[c.external.provider] ?? c.external.provider}’dan</>
                )}
                {c.external.push_error ? (
                  <span className="text-red-700" title={c.external.push_error}>· geri yazılamadı</span>
                ) : c.external.pending_push ? (
                  <span>· geri yazılıyor…</span>
                ) : null}
              </span>
            )}
          </p>
        </div>
        <CardTimerButton cardId={c.id} />
        <button onClick={onClose} aria-label="Kapat" className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-800">
          <X size={20} aria-hidden />
        </button>
      </div>

      <div className="grid gap-x-8 lg:grid-cols-[minmax(0,1fr)_300px]">
        {/* ---------- sol: kartin icerigi ---------- */}
        <div className="min-w-0">
          {/* Aciklama */}
          <div className="mt-5">
            <h3 className={sectionTitle}>Açıklama</h3>
            {editingDesc ? (
              <MarkdownEditor
                autoFocus
                minRows={6}
                placeholder="Markdown destekli…"
                value={description}
                onChange={setDescription}
                onSubmit={saveDescription}
                onCancel={cancelDescription}
                onFiles={(files) => uploads.upload(files)}
              />
            ) : (
              <div
                role="button"
                tabIndex={0}
                onClick={(e) => !(e.target as HTMLElement).closest('a,button') && setEditingDesc(true)}
                onDoubleClick={(e) => !(e.target as HTMLElement).closest('a,button') && setEditingDesc(true)}
                onKeyDown={(e) => e.key === 'Enter' && e.target === e.currentTarget && setEditingDesc(true)}
                className="min-h-14 cursor-text rounded-md border border-transparent bg-slate-50 px-3 py-2 text-[15px] hover:border-slate-200"
              >
                {c.description ? <MarkdownView content={c.description} attachments={c.attachments} /> : <span className="text-slate-500">Açıklama eklemek için tıkla</span>}
              </div>
            )}
          </div>

          {/* Checklist */}
          <div className={section}>
            <h3 className={sectionTitle}>
              Yapılacaklar {c.checklist_total > 0 && <span className="font-normal text-slate-500 tabular-nums">{c.checklist_done}/{c.checklist_total}</span>}
            </h3>
            {c.checklist_total > 0 && (
              <div className="mb-2 h-1.5 rounded-full bg-slate-200" aria-hidden>
                <div className="h-1.5 rounded-full bg-green-700" style={{ width: `${(c.checklist_done / c.checklist_total) * 100}%` }} />
              </div>
            )}
            <ul className="space-y-1">
              {c.checklist.map((i) => (
                <li key={i.id} className="group flex items-center gap-2 text-[15px]">
                  <input type="checkbox" checked={i.is_done} onChange={() => m.updateItem.mutate({ id: i.id, is_done: !i.is_done })} aria-label={i.text} />
                  <span className={`flex-1 ${i.is_done ? 'text-slate-500 line-through' : ''}`}>{i.text}</span>
                  <button onClick={() => m.deleteItem.mutate(i.id)} className="rounded p-0.5 text-slate-400 opacity-0 group-hover:opacity-100 focus:opacity-100 hover:text-red-700" aria-label={`${i.text} maddesini sil`}>
                    <X size={14} aria-hidden />
                  </button>
                </li>
              ))}
            </ul>
            <form onSubmit={addItem} className="mt-2">
              <input className={input} placeholder="Madde ekle ve Enter'a bas" maxLength={500} value={item} onChange={(e) => setItem(e.target.value)} />
            </form>
          </div>

          {/* Alt kartlar */}
          <div className={section}>
            <div className="mb-2 flex items-baseline justify-between gap-3">
              <h3 className="text-[15px] font-semibold text-slate-900">
                Alt kartlar{' '}
                {c.subtask_total > 0 && (
                  <span className="font-normal text-slate-500 tabular-nums">
                    {c.subtask_done}/{c.subtask_total}
                    {c.subtask_estimated_minutes > 0 && `, toplam ${hours(c.subtask_estimated_minutes)} saat`}
                  </span>
                )}
              </h3>
              <button onClick={() => setSplitOpen((o) => !o)} aria-expanded={splitOpen} className="text-[13px] text-blue-700 hover:underline">
                Parçalara böl
              </button>
            </div>
            {splitOpen && (
              <form onSubmit={submitSplit} className="mb-3 flex flex-wrap items-end gap-3 rounded-md border border-dashed border-slate-300 p-3 text-sm">
                <label className="space-y-1">
                  <span className={fieldLabel}>Parça sayısı</span>
                  <input type="number" min={1} max={50} required className="w-20 rounded border border-slate-300 px-2 py-1" value={splitParts} onChange={(e) => setSplitParts(e.target.value)} />
                </label>
                <label className="space-y-1">
                  <span className={fieldLabel}>Toplam süre (saat)</span>
                  <input inputMode="decimal" className="w-24 rounded border border-slate-300 px-2 py-1" placeholder={c.estimated_minutes ? String(hours(c.estimated_minutes)) : 'ör. 20'} value={splitHours} onChange={(e) => setSplitHours(e.target.value)} />
                </label>
                <label className="flex items-center gap-1.5 pb-1">
                  <input type="checkbox" checked={splitChain} onChange={(e) => setSplitChain(e.target.checked)} />
                  Sırayla bağla
                </label>
                <button disabled={m.split.isPending} className="rounded-md bg-slate-900 px-3 py-1 text-white disabled:opacity-50">Böl</button>
                {m.split.error && <span className="text-red-700">{m.split.error.message}</span>}
              </form>
            )}
            <ul className="divide-y divide-slate-100">
              {c.subtasks.map((st) => (
                <li key={st.id} className="flex items-center gap-2 py-1 text-[15px]">
                  <StatusMark status={st.status} blocked={st.blocked} />
                  <button onClick={() => onOpenCard(st.id)} className={`flex-1 text-left hover:underline ${st.status === 'completed' ? 'text-slate-500 line-through' : ''}`}>
                    {st.title}
                  </button>
                  {st.estimated_minutes != null && <span className="text-[13px] text-slate-500 tabular-nums">{st.estimated_minutes} dk</span>}
                </li>
              ))}
            </ul>
            <form onSubmit={addSubtask} className="mt-2">
              <input className={input} placeholder="Alt kart ekle ve Enter'a bas" maxLength={200} value={subtask} onChange={(e) => setSubtask(e.target.value)} />
            </form>
          </div>

          {/* Ekler */}
          <AttachmentsSection
            cardId={c.id}
            boardId={board.board.id}
            attachments={c.attachments}
            pending={uploads.pending}
            error={uploads.error}
            onFiles={(files) => void uploads.upload(files)}
          />

          {/* Notlar */}
          <div className={section}>
            <h3 className={sectionTitle}>Notlar</h3>
            <MarkdownEditor
              minRows={2}
              placeholder="Not ekle"
              value={note}
              onChange={setNote}
              onSubmit={addNote}
              submitLabel="Notu kaydet"
              onFiles={(files) => uploads.upload(files)}
            />
            <ul className="mt-3 space-y-3">
              {c.notes.map((n) => {
                const edited = new Date(n.updated_at).getTime() - new Date(n.created_at).getTime() > 5000
                return (
                  <li key={n.id} className="group border-l-2 border-slate-300 pl-3 text-[15px]">
                    <div className="mb-0.5 flex justify-between text-[12px] text-slate-500">
                      <span>
                        {formatDateTime(n.created_at)}
                        {edited && ' (düzenlendi)'}
                      </span>
                      {editingNote !== n.id && (
                        <span className="flex gap-3 opacity-0 group-focus-within:opacity-100 group-hover:opacity-100">
                          <button onClick={() => startEditNote(n.id, n.content)} className="hover:text-slate-900">Düzenle</button>
                          <button onClick={() => m.deleteNote.mutate(n.id)} className="hover:text-red-700">Sil</button>
                        </span>
                      )}
                    </div>
                    {editingNote === n.id ? (
                      <MarkdownEditor
                        autoFocus
                        value={noteDraft}
                        onChange={setNoteDraft}
                        onSubmit={() => saveNote(n.id, n.content)}
                        onCancel={() => cancelNote(n.content)}
                        onFiles={(files) => uploads.upload(files, n.id)}
                      />
                    ) : (
                      <div onDoubleClick={(e) => onNoteDoubleClick(e, n.id, n.content)} title="Düzenlemek için çift tıkla">
                        <MarkdownView content={n.content} attachments={c.attachments} />
                      </div>
                    )}
                  </li>
                )
              })}
            </ul>
            {m.updateNote.error && <p className="mt-1 text-sm text-red-700">{m.updateNote.error.message}</p>}
          </div>

          {/* Gecmis */}
          <div className={section}>
            <button onClick={() => setShowHistory((s) => !s)} aria-expanded={showHistory} className="text-[14px] text-slate-600 hover:underline">
              {showHistory ? 'Geçmişi gizle' : 'Geçmişi göster'}
            </button>
            {showHistory && (
              <ul className="mt-2 space-y-1 text-[13px] text-slate-600">
                {activity.data?.map((a) => (
                  <li key={a.id} className="flex gap-3">
                    <span className="shrink-0 text-slate-500 tabular-nums">{formatDateTime(a.occurred_at)}</span>
                    <span>
                      {a.entity_type === 'note' ? `not ${NOTE_ACTION[a.action] ?? a.action}` : ACTION_LABEL[a.action] ?? a.action}
                      {a.actor !== 'user' && ` (${a.actor === 'ai' ? 'asistan' : a.actor})`}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* ---------- sag: kunye ---------- */}
        <aside className="min-w-0 lg:border-l lg:border-slate-200 lg:pl-6">
          <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-1">
            <label className="space-y-1">
              <span className={fieldLabel}>Öncelik</span>
              <select className={input} value={c.priority} onChange={(e) => m.update.mutate({ priority: e.target.value as TaskPriority })}>
                {(Object.keys(PRIORITY_LABEL) as TaskPriority[]).map((p) => (
                  <option key={p} value={p}>{PRIORITY_LABEL[p]}</option>
                ))}
              </select>
            </label>
            <label className="space-y-1">
              <span className={fieldLabel}>Son tarih</span>
              <input type="date" className={input} value={toDateInput(c.due_date)} onChange={(e) => m.update.mutate({ due_date: fromDateInput(e.target.value) })} />
            </label>
            <label className="space-y-1">
              <span className={fieldLabel}>Tahmini süre (dakika)</span>
              <input
                type="number"
                min={0}
                className={input}
                defaultValue={c.estimated_minutes ?? ''}
                key={c.estimated_minutes ?? 'empty'}
                onBlur={(e) => {
                  const v = e.target.value === '' ? null : Number(e.target.value)
                  if (v !== c.estimated_minutes) m.update.mutate({ estimated_minutes: v })
                }}
              />
            </label>
            <div className="col-span-2 space-y-1 lg:col-span-1">
              <RecurrencePicker
                key={`${c.id}-${c.recurrence_rule ?? ''}`}
                value={c.recurrence_rule}
                onChange={(rule) => rule !== c.recurrence_rule && m.recurrence.mutate(rule)}
                startDay={dayCodeOf(c.due_date ? new Date(c.due_date) : new Date())}
                inputClass={input}
              />
              {c.series_id != null && (
                <p className="text-[13px] text-slate-600">
                  Serinin {c.series_index}. kartı; seri {c.series_done_count} kez tamamlandı.
                  {c.recurrence_rule &&
                    (c.status === 'completed' ? ' Sıradaki kart açıldı.' : ' Bitince sıradaki kart kendiliğinden açılır.')}
                </p>
              )}
              {m.recurrence.error && <p className="text-[13px] text-red-700">{m.recurrence.error.message}</p>}
            </div>
            <div className="space-y-1">
              <span className={fieldLabel}>Etiketler</span>
              <div className="flex flex-wrap gap-1">
                {board.labels.length === 0 && <span className="text-[13px] text-slate-500">Board ayarlarından eklenir</span>}
                {board.labels.map((l) => {
                  const on = c.label_ids.includes(l.id)
                  return (
                    <button
                      key={l.id}
                      aria-pressed={on}
                      onClick={() => toggleLabel(l.id)}
                      className={`rounded px-2 py-0.5 text-[13px] ${on ? 'text-white' : 'text-slate-700 ring-1 ring-slate-300'}`}
                      style={on ? { backgroundColor: l.color } : undefined}
                    >
                      {l.name}
                    </button>
                  )
                })}
              </div>
            </div>
          </div>

          <CardTime card={c} />

          <CardSchedule cardId={c.id} estimatedMinutes={c.estimated_minutes} />

          {/* Bagimliliklar */}
          <div className={section}>
            <h3 className={sectionTitle}>Önce bitmesi gerekenler</h3>
            {c.blocked && (
              <p className="-mt-1 mb-2 inline-flex items-center gap-1 text-[13px] text-amber-800">
                <Hourglass size={13} aria-hidden /> Bu kart bekliyor
              </p>
            )}
            <ul className="space-y-1 text-[14px]">
              {c.depends_on.map((d) => (
                <li key={d.id} className="group flex items-center gap-2">
                  <StatusMark status={d.status} blocked={d.status !== 'completed'} />
                  <button onClick={() => onOpenCard(d.id)} className="flex-1 text-left hover:underline">{d.title}</button>
                  <button onClick={() => m.removeDependency.mutate(d.id)} className="rounded p-0.5 text-slate-400 opacity-0 group-hover:opacity-100 focus:opacity-100 hover:text-red-700" aria-label={`${d.title} bağını kaldır`}>
                    <X size={14} aria-hidden />
                  </button>
                </li>
              ))}
            </ul>
            {depCandidates.length > 0 && (
              <div className="mt-2 flex gap-2">
                <select className={`${input} min-w-0 flex-1`} value={depChoice} onChange={(e) => setDepChoice(e.target.value)} aria-label="Ön koşul seç">
                  <option value="">Ön koşul seç</option>
                  {depCandidates.map((x) => (
                    <option key={x.id} value={x.id}>{x.title}</option>
                  ))}
                </select>
                <button
                  disabled={!depChoice}
                  onClick={() => m.addDependency.mutate(Number(depChoice), { onSuccess: () => setDepChoice('') })}
                  className="rounded-md border border-slate-300 px-3 text-sm disabled:opacity-40"
                >
                  Bağla
                </button>
              </div>
            )}
            {m.addDependency.error && <p className="mt-1 text-sm text-red-700">{m.addDependency.error.message}</p>}
            {c.dependents.length > 0 && (
              <p className="mt-2 text-[13px] text-slate-600">
                Bu kartı bekleyenler:{' '}
                {c.dependents.map((d, i) => (
                  <span key={d.id}>
                    {i > 0 && ', '}
                    <button onClick={() => onOpenCard(d.id)} className="hover:underline">{d.title}</button>
                  </span>
                ))}
              </p>
            )}
          </div>

          {/* Eylemler */}
          <div className="mt-8 flex justify-between border-t border-slate-200 pt-4 text-sm">
            <button onClick={() => m.update.mutate({ is_archived: true }, { onSuccess: onClose })} className="text-slate-700 hover:underline">
              Arşivle
            </button>
            <button
              onClick={() => confirm('Kart kalıcı olarak silinsin mi?') && m.remove.mutate(undefined, { onSuccess: onClose })}
              className="text-red-700 hover:underline"
            >
              Kalıcı olarak sil
            </button>
          </div>
          {m.update.error && <p className="mt-2 text-sm text-red-700">{m.update.error.message}</p>}
        </aside>
      </div>
      </div>
    </Modal>
  )
}
