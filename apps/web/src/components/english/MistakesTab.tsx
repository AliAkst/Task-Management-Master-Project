import { useState } from 'react'
import { Trash2 } from 'lucide-react'
import { CATEGORY_LABELS, SOURCE_LABELS, useDeleteMistake, useMistakes } from '../../api/english'

const date = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short', year: 'numeric' })

export default function MistakesTab() {
  const [category, setCategory] = useState('')
  const list = useMistakes(category)
  const del = useDeleteMistake()

  return (
    <div className="space-y-4">
      <label className="flex items-center gap-2 text-sm">
        Kategori
        <select
          className="rounded-md border border-slate-300 bg-surface px-2 py-1"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        >
          <option value="">Hepsi</option>
          {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
      </label>
      {list.isPending && <p className="text-slate-600">Yükleniyor…</p>}
      {list.isError && <p role="alert" className="text-red-700">Hata günlüğü yüklenemedi.</p>}
      {list.data && list.data.length === 0 && <p className="text-slate-600">Kayıtlı hata yok.</p>}
      {del.isError && <p role="alert" className="text-sm text-red-700">Silinemedi, tekrar dene</p>}
      <ul className="space-y-2">
        {list.data?.map((m) => (
          <li key={m.id} className="flex items-start gap-3 rounded-xl border border-slate-200 bg-surface p-3">
            <div className="min-w-0 flex-1 text-[15px]">
              <p>
                <span className="text-slate-600">{m.original}</span> → <span className="font-semibold">{m.corrected}</span>
              </p>
              {m.explanation_tr && <p className="text-sm text-slate-600">{m.explanation_tr}</p>}
              <p className="mt-1 text-xs text-slate-500">
                {CATEGORY_LABELS[m.category] ?? m.category} · {SOURCE_LABELS[m.source] ?? m.source} ·{' '}
                {date.format(new Date(m.created_at))}
              </p>
            </div>
            <button
              aria-label="Hatayı sil"
              title="Sil"
              disabled={del.isPending}
              onClick={() => del.mutate(m.id)}
              className="rounded p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-900 disabled:opacity-40"
            >
              <Trash2 size={16} aria-hidden />
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
