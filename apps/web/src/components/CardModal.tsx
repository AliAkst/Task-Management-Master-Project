import { useEffect, useState, type FormEvent } from 'react'
import Markdown from 'react-markdown'
import { useCard, useCardActivity, useCardMutations } from '../api/boards'
import {
  ACTION_LABEL,
  formatDateTime,
  fromDateInput,
  PRIORITY_LABEL,
  toDateInput,
} from '../lib/format'
import type { BoardDetail, TaskPriority } from '../lib/types'
import CardSchedule from './CardSchedule'
import CardTime, { CardTimerButton } from './CardTime'
import Modal from './Modal'

interface Props {
  cardId: number
  board: BoardDetail
  onClose: () => void
  onOpenCard: (id: number) => void
}

const section = 'mt-6'
const sectionTitle = 'mb-2 text-sm font-medium text-slate-700'

export default function CardModal({ cardId, board, onClose, onOpenCard }: Props) {
  const card = useCard(cardId)
  const activity = useCardActivity(cardId)
  const m = useCardMutations(cardId, board.board.id)

  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [editingDesc, setEditingDesc] = useState(false)
  const [note, setNote] = useState('')
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
  const addNote = (e: FormEvent) => {
    e.preventDefault()
    if (note.trim()) m.addNote.mutate(note.trim(), { onSuccess: () => setNote('') })
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

  return (
    <Modal wide onClose={onClose}>
      {/* Baslik */}
      <div className="flex items-start gap-3">
        <button
          title={done ? 'Yeniden aç' : 'Tamamla'}
          onClick={() => m.update.mutate({ status: done ? 'pending' : 'completed' })}
          className={`mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2 ${
            done ? 'border-green-600 bg-green-600 text-white' : 'border-slate-300 hover:border-green-600'
          }`}
        >
          {done && '✓'}
        </button>
        <div className="flex-1">
          <input
            className="w-full rounded px-1 text-xl font-semibold focus:outline-slate-300"
            value={title}
            maxLength={200}
            onChange={(e) => setTitle(e.target.value)}
            onBlur={saveTitle}
            onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
          />
          <p className="px-1 text-xs text-slate-500">
            {list ? `“${list.name}” listesinde` : 'Listesiz'}
            {c.parent && (
              <>
                {' · '}
                <button className="text-blue-600 hover:underline" onClick={() => onOpenCard(c.parent!.id)}>
                  ↑ {c.parent.title}
                </button>
              </>
            )}
            {c.created_by === 'ai' && ' · AI tarafından oluşturuldu'}
            {c.completed_at && ` · ${formatDateTime(c.completed_at)} tarihinde tamamlandı`}
          </p>
        </div>
        <CardTimerButton cardId={c.id} />
        <button onClick={onClose} aria-label="Kapat" className="text-xl text-slate-400 hover:text-slate-700">
          ×
        </button>
      </div>

      {/* Ozellikler */}
      <div className="mt-5 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <label className="space-y-1">
          <span className="text-xs text-slate-500">Öncelik</span>
          <select
            className="w-full rounded-md border border-slate-300 px-2 py-1"
            value={c.priority}
            onChange={(e) => m.update.mutate({ priority: e.target.value as TaskPriority })}
          >
            {(Object.keys(PRIORITY_LABEL) as TaskPriority[]).map((p) => (
              <option key={p} value={p}>{PRIORITY_LABEL[p]}</option>
            ))}
          </select>
        </label>
        <label className="space-y-1">
          <span className="text-xs text-slate-500">Son tarih</span>
          <input
            type="date"
            className="w-full rounded-md border border-slate-300 px-2 py-1"
            value={toDateInput(c.due_date)}
            onChange={(e) => m.update.mutate({ due_date: fromDateInput(e.target.value) })}
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs text-slate-500">Tahmini süre (dk)</span>
          <input
            type="number"
            min={0}
            className="w-full rounded-md border border-slate-300 px-2 py-1"
            defaultValue={c.estimated_minutes ?? ''}
            key={c.estimated_minutes ?? 'empty'}
            onBlur={(e) => {
              const v = e.target.value === '' ? null : Number(e.target.value)
              if (v !== c.estimated_minutes) m.update.mutate({ estimated_minutes: v })
            }}
          />
        </label>
        <div className="space-y-1">
          <span className="text-xs text-slate-500">Etiketler</span>
          <div className="flex flex-wrap gap-1">
            {board.labels.length === 0 && <span className="text-xs text-slate-400">Board ayarlarından ekle</span>}
            {board.labels.map((l) => {
              const on = c.label_ids.includes(l.id)
              return (
                <button
                  key={l.id}
                  onClick={() => toggleLabel(l.id)}
                  className={`rounded px-1.5 py-0.5 text-xs ${on ? 'text-white' : 'text-slate-600 ring-1 ring-slate-300'}`}
                  style={on ? { backgroundColor: l.color } : undefined}
                >
                  {l.name}
                </button>
              )
            })}
          </div>
        </div>
      </div>

      {/* Aciklama */}
      <div className={section}>
        <h3 className={sectionTitle}>Açıklama</h3>
        {editingDesc ? (
          <div className="space-y-2">
            <textarea
              autoFocus
              rows={8}
              className="w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-sm"
              placeholder="Markdown destekli…"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
            <div className="flex gap-2">
              <button onClick={saveDescription} className="rounded-md bg-slate-900 px-3 py-1 text-sm text-white">Kaydet</button>
              <button onClick={() => { setDescription(c.description ?? ''); setEditingDesc(false) }} className="text-sm text-slate-500">Vazgeç</button>
            </div>
          </div>
        ) : (
          <div
            onClick={() => setEditingDesc(true)}
            className="prose-sm min-h-12 cursor-text rounded-md bg-slate-50 px-3 py-2 text-sm hover:bg-slate-100 [&_a]:text-blue-600 [&_li]:ml-4 [&_ol]:list-decimal [&_ul]:list-disc"
          >
            {c.description ? <Markdown>{c.description}</Markdown> : <span className="text-slate-400">Açıklama eklemek için tıkla…</span>}
          </div>
        )}
      </div>

      {/* Checklist */}
      <div className={section}>
        <h3 className={sectionTitle}>
          Checklist {c.checklist_total > 0 && <span className="font-normal text-slate-400">({c.checklist_done}/{c.checklist_total})</span>}
        </h3>
        {c.checklist_total > 0 && (
          <div className="mb-2 h-1.5 rounded-full bg-slate-200">
            <div className="h-1.5 rounded-full bg-green-500" style={{ width: `${(c.checklist_done / c.checklist_total) * 100}%` }} />
          </div>
        )}
        <ul className="space-y-1">
          {c.checklist.map((i) => (
            <li key={i.id} className="group flex items-center gap-2 text-sm">
              <input type="checkbox" checked={i.is_done} onChange={() => m.updateItem.mutate({ id: i.id, is_done: !i.is_done })} />
              <span className={`flex-1 ${i.is_done ? 'text-slate-400 line-through' : ''}`}>{i.text}</span>
              <button onClick={() => m.deleteItem.mutate(i.id)} className="text-slate-400 opacity-0 group-hover:opacity-100 hover:text-red-600" aria-label="Sil">×</button>
            </li>
          ))}
        </ul>
        <form onSubmit={addItem} className="mt-2">
          <input className="w-full rounded-md border border-slate-300 px-2 py-1 text-sm" placeholder="+ Madde ekle" maxLength={500} value={item} onChange={(e) => setItem(e.target.value)} />
        </form>
      </div>

      <CardTime card={c} />

      <CardSchedule cardId={c.id} estimatedMinutes={c.estimated_minutes} />

      {/* Alt kartlar */}
      <div className={section}>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-medium text-slate-700">
            Alt kartlar{' '}
            {c.subtask_total > 0 && (
              <span className="font-normal text-slate-400">
                ({c.subtask_done}/{c.subtask_total}
                {c.subtask_estimated_minutes > 0 && ` · ${hours(c.subtask_estimated_minutes)} saat`})
              </span>
            )}
          </h3>
          <button onClick={() => setSplitOpen((o) => !o)} className="text-xs text-blue-600 hover:underline">
            Parçalara böl
          </button>
        </div>
        {splitOpen && (
          <form onSubmit={submitSplit} className="mb-3 flex flex-wrap items-end gap-3 rounded-md bg-slate-50 p-3 text-sm">
            <label className="space-y-1">
              <span className="block text-xs text-slate-500">Parça sayısı</span>
              <input type="number" min={1} max={50} required className="w-20 rounded border border-slate-300 px-2 py-1" value={splitParts} onChange={(e) => setSplitParts(e.target.value)} />
            </label>
            <label className="space-y-1">
              <span className="block text-xs text-slate-500">Toplam süre (saat)</span>
              <input inputMode="decimal" className="w-24 rounded border border-slate-300 px-2 py-1" placeholder={c.estimated_minutes ? String(hours(c.estimated_minutes)) : 'ör. 20'} value={splitHours} onChange={(e) => setSplitHours(e.target.value)} />
            </label>
            <label className="flex items-center gap-1.5 pb-1">
              <input type="checkbox" checked={splitChain} onChange={(e) => setSplitChain(e.target.checked)} />
              Sırayla bağla
            </label>
            <button disabled={m.split.isPending} className="rounded-md bg-slate-900 px-3 py-1 text-white disabled:opacity-50">Böl</button>
            {m.split.error && <span className="text-red-600">{m.split.error.message}</span>}
          </form>
        )}
        <ul className="space-y-1">
          {c.subtasks.map((st) => (
            <li key={st.id} className="flex items-center gap-2 text-sm">
              <span className={st.status === 'completed' ? 'text-green-600' : st.blocked ? 'text-amber-500' : 'text-slate-300'}>
                {st.status === 'completed' ? '✓' : st.blocked ? '⛓' : '○'}
              </span>
              <button onClick={() => onOpenCard(st.id)} className={`flex-1 text-left hover:underline ${st.status === 'completed' ? 'text-slate-400 line-through' : ''}`}>
                {st.title}
              </button>
              {st.estimated_minutes != null && <span className="text-xs text-slate-400">{st.estimated_minutes} dk</span>}
            </li>
          ))}
        </ul>
        <form onSubmit={addSubtask} className="mt-2">
          <input className="w-full rounded-md border border-slate-300 px-2 py-1 text-sm" placeholder="+ Alt kart ekle" maxLength={200} value={subtask} onChange={(e) => setSubtask(e.target.value)} />
        </form>
      </div>

      {/* Bagimliliklar */}
      <div className={section}>
        <h3 className={sectionTitle}>
          Önce bitmesi gerekenler{' '}
          {c.blocked && <span className="font-normal text-amber-600">· bu kart bekliyor</span>}
        </h3>
        <ul className="space-y-1 text-sm">
          {c.depends_on.map((d) => (
            <li key={d.id} className="group flex items-center gap-2">
              <span className={d.status === 'completed' ? 'text-green-600' : 'text-amber-500'}>
                {d.status === 'completed' ? '✓' : '⛓'}
              </span>
              <button onClick={() => onOpenCard(d.id)} className="flex-1 text-left hover:underline">{d.title}</button>
              <button onClick={() => m.removeDependency.mutate(d.id)} className="text-slate-400 opacity-0 group-hover:opacity-100 hover:text-red-600" aria-label="Bağı kaldır">×</button>
            </li>
          ))}
        </ul>
        {depCandidates.length > 0 && (
          <div className="mt-2 flex gap-2">
            <select className="flex-1 rounded-md border border-slate-300 px-2 py-1 text-sm" value={depChoice} onChange={(e) => setDepChoice(e.target.value)}>
              <option value="">Ön koşul seç…</option>
              {depCandidates.map((x) => (
                <option key={x.id} value={x.id}>{x.title}</option>
              ))}
            </select>
            <button
              disabled={!depChoice}
              onClick={() => m.addDependency.mutate(Number(depChoice), { onSuccess: () => setDepChoice('') })}
              className="rounded-md bg-slate-200 px-3 py-1 text-sm disabled:opacity-50"
            >
              Bağla
            </button>
          </div>
        )}
        {m.addDependency.error && <p className="mt-1 text-sm text-red-600">{m.addDependency.error.message}</p>}
        {c.dependents.length > 0 && (
          <p className="mt-2 text-xs text-slate-500">
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

      {/* Notlar */}
      <div className={section}>
        <h3 className={sectionTitle}>Notlar</h3>
        <form onSubmit={addNote} className="space-y-2">
          <textarea
            rows={2}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            placeholder="Not ekle… (Ctrl+Enter ile kaydet)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && e.ctrlKey && addNote(e)}
          />
          {note.trim() && <button className="rounded-md bg-slate-900 px-3 py-1 text-sm text-white">Kaydet</button>}
        </form>
        <ul className="mt-3 space-y-3">
          {c.notes.map((n) => (
            <li key={n.id} className="group rounded-md bg-slate-50 px-3 py-2 text-sm">
              <div className="mb-1 flex justify-between text-xs text-slate-400">
                <span>{formatDateTime(n.created_at)}</span>
                <button onClick={() => m.deleteNote.mutate(n.id)} className="opacity-0 group-hover:opacity-100 hover:text-red-600">Sil</button>
              </div>
              <div className="[&_li]:ml-4 [&_ul]:list-disc"><Markdown>{n.content}</Markdown></div>
            </li>
          ))}
        </ul>
      </div>

      {/* Gecmis */}
      <div className={section}>
        <button onClick={() => setShowHistory((s) => !s)} className="text-sm text-slate-500 hover:underline">
          {showHistory ? 'Geçmişi gizle' : 'Geçmişi göster'}
        </button>
        {showHistory && (
          <ul className="mt-2 space-y-1 text-xs text-slate-500">
            {activity.data?.map((a) => (
              <li key={a.id}>
                <span className="text-slate-400">{formatDateTime(a.occurred_at)}</span> ·{' '}
                {a.entity_type === 'note' ? 'not eklendi' : ACTION_LABEL[a.action] ?? a.action}
                {a.actor !== 'user' && ` (${a.actor})`}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Eylemler */}
      <div className="mt-6 flex justify-between border-t border-slate-200 pt-4 text-sm">
        <button onClick={() => m.update.mutate({ is_archived: true }, { onSuccess: onClose })} className="text-slate-600 hover:underline">
          Arşivle
        </button>
        <button
          onClick={() => confirm('Kart kalıcı olarak silinsin mi?') && m.remove.mutate(undefined, { onSuccess: onClose })}
          className="text-red-600 hover:underline"
        >
          Sil
        </button>
      </div>
      {m.update.error && <p className="mt-2 text-sm text-red-600">{m.update.error.message}</p>}
    </Modal>
  )
}
