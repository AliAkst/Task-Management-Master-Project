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
import Modal from './Modal'

interface Props {
  cardId: number
  board: BoardDetail
  onClose: () => void
}

const section = 'mt-6'
const sectionTitle = 'mb-2 text-sm font-medium text-slate-700'

export default function CardModal({ cardId, board, onClose }: Props) {
  const card = useCard(cardId)
  const activity = useCardActivity(cardId)
  const m = useCardMutations(cardId, board.board.id)

  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [editingDesc, setEditingDesc] = useState(false)
  const [note, setNote] = useState('')
  const [item, setItem] = useState('')
  const [showHistory, setShowHistory] = useState(false)

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
            {c.created_by === 'ai' && ' · AI tarafından oluşturuldu'}
            {c.completed_at && ` · ${formatDateTime(c.completed_at)} tarihinde tamamlandı`}
          </p>
        </div>
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
