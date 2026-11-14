import { useMemo, useState } from 'react'
import { Check, Copy } from 'lucide-react'
import { useBoards } from '../api/boards'
import { useWorkSummary } from '../api/workSummary'
import MarkdownView from './MarkdownView'
import Modal from './Modal'

const STORE_KEY = 'work-summary-boards'

/** Tarayicida hatirlanan board secimi; null = tum board'lar. Depolama yoksa sessizce null. */
function readSaved(): number[] | null {
  try {
    const raw = localStorage.getItem(STORE_KEY)
    if (!raw) return null
    const v: unknown = JSON.parse(raw)
    return Array.isArray(v) && v.every((x) => typeof x === 'number') ? (v as number[]) : null
  } catch {
    return null
  }
}

function save(ids: number[] | null) {
  try {
    if (ids === null) localStorage.removeItem(STORE_KEY)
    else localStorage.setItem(STORE_KEY, JSON.stringify(ids))
  } catch {
    /* depolama kapali: secim yalniz bu pencerede kalir */
  }
}

/** Gun sonu is ozeti: board secimi + Markdown onizleme + Trello'ya yapistirmak icin kopyala. */
export default function WorkSummaryDialog({ day, onClose }: { day: string; onClose: () => void }) {
  const boards = useBoards()
  const [saved, setSaved] = useState<number[] | null>(readSaved)
  const [copy, setCopy] = useState<'idle' | 'ok' | 'fail'>('idle')

  const all = useMemo(() => (boards.data ?? []).map((b) => b.id), [boards.data])
  // Silinmis board id'leri secimden dusulur; bos secim = tum board'lar
  const selected = useMemo(() => {
    if (saved === null) return null
    const alive = saved.filter((id) => all.includes(id))
    return alive.length ? alive : null
  }, [saved, all])
  const summary = useWorkSummary(day, boards.isSuccess ? selected : null)

  const toggle = (id: number) => {
    const current = selected ?? all
    const next = current.includes(id) ? current.filter((x) => x !== id) : [...current, id]
    const value = next.length === 0 || next.length === all.length ? null : next
    setSaved(value)
    save(value)
    setCopy('idle')
  }

  const doCopy = () => {
    if (!summary.data) return
    navigator.clipboard
      .writeText(summary.data.text)
      .then(() => setCopy('ok'))
      .catch(() => setCopy('fail'))
  }

  return (
    <Modal title="İş özeti" size="lg" onClose={onClose}>
      <fieldset className="mb-4">
        <legend className="mb-1 text-sm font-medium text-slate-700">Board'lar</legend>
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          {(boards.data ?? []).map((b) => (
            <label key={b.id} className="inline-flex items-center gap-1.5 text-sm">
              <input
                type="checkbox"
                checked={selected === null || selected.includes(b.id)}
                onChange={() => toggle(b.id)}
              />
              {b.name}
            </label>
          ))}
        </div>
      </fieldset>

      {summary.isLoading && <p className="text-slate-500">Hazırlanıyor…</p>}
      {summary.error && <p className="text-red-600">{summary.error.message}</p>}
      {summary.data && (
        <div className="rounded-md border border-slate-200 bg-surface p-4 text-[15px]">
          <MarkdownView content={summary.data.text} />
        </div>
      )}

      <div className="mt-4 flex items-center justify-end gap-3">
        <span role="status" className="text-sm text-slate-600">
          {copy === 'ok' && 'Kopyalandı'}
          {copy === 'fail' && 'Kopyalanamadı — metni seçip kopyala'}
        </span>
        <button onClick={onClose} className="rounded-md px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-200">
          Kapat
        </button>
        <button
          onClick={doCopy}
          disabled={!summary.data}
          className="inline-flex items-center gap-1.5 rounded-md bg-slate-900 px-3 py-1.5 text-sm text-on-ink disabled:opacity-50"
        >
          {copy === 'ok' ? <Check size={15} aria-hidden /> : <Copy size={15} aria-hidden />}
          Kopyala
        </button>
      </div>
      <p className="mt-2 text-xs text-slate-500">Trello'ya yazılmaz; metni kopyalayıp kendin yapıştırırsın.</p>
    </Modal>
  )
}
