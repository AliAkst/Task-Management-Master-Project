import { useState, type FormEvent } from 'react'
import type { BoardCreate } from '../lib/types'

export const COLORS = [
  '#64748b', '#ef4444', '#f97316', '#eab308', '#22c55e',
  '#14b8a6', '#3b82f6', '#6366f1', '#a855f7', '#ec4899',
]

interface Props {
  initial?: Partial<BoardCreate>
  submitLabel: string
  busy?: boolean
  onSubmit: (data: BoardCreate) => void
  onCancel?: () => void
}

/** Board olusturma / duzenleme formu. */
export default function BoardForm({ initial, submitLabel, busy, onSubmit, onCancel }: Props) {
  const [name, setName] = useState(initial?.name ?? '')
  const [scope, setScope] = useState(initial?.scope_description ?? '')
  const [color, setColor] = useState(initial?.color ?? COLORS[6])
  const [budgetHours, setBudgetHours] = useState(
    initial?.weekly_time_budget_min ? String(initial.weekly_time_budget_min / 60) : '',
  )
  const [privacy, setPrivacy] = useState(initial?.privacy ?? 'cloud_allowed')

  function submit(e: FormEvent) {
    e.preventDefault()
    const hours = parseFloat(budgetHours.replace(',', '.'))
    onSubmit({
      name: name.trim(),
      scope_description: scope.trim() || null,
      color,
      weekly_time_budget_min: Number.isFinite(hours) ? Math.round(hours * 60) : null,
      privacy,
    })
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <input
        autoFocus
        required
        maxLength={100}
        className="w-full rounded-md border border-slate-300 px-3 py-2"
        placeholder="Board adı (ör. Spor)"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <textarea
        rows={3}
        className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
        placeholder="Bu alana neler girer? (AI işleri doğru board'a koymak için kullanır)"
        value={scope}
        onChange={(e) => setScope(e.target.value)}
      />
      <div className="flex flex-wrap items-center gap-2">
        {COLORS.map((c) => (
          <button
            type="button"
            key={c}
            aria-label={`Renk ${c}`}
            onClick={() => setColor(c)}
            className={`h-6 w-6 rounded-full ${color === c ? 'ring-2 ring-slate-900 ring-offset-2' : ''}`}
            style={{ backgroundColor: c }}
          />
        ))}
      </div>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <label className="space-y-1">
          <span className="text-slate-600">Haftalık süre hedefi (saat)</span>
          <input
            inputMode="decimal"
            className="w-full rounded-md border border-slate-300 px-3 py-2"
            placeholder="ör. 5"
            value={budgetHours}
            onChange={(e) => setBudgetHours(e.target.value)}
          />
        </label>
        <label className="space-y-1">
          <span className="text-slate-600">AI gizliliği</span>
          <select
            className="w-full rounded-md border border-slate-300 px-3 py-2"
            value={privacy}
            onChange={(e) => setPrivacy(e.target.value as typeof privacy)}
          >
            <option value="cloud_allowed">Tüm modeller görebilir</option>
            <option value="local_only">Sadece local model</option>
          </select>
        </label>
      </div>
      <div className="flex justify-end gap-2">
        {onCancel && (
          <button type="button" onClick={onCancel} className="px-3 py-2 text-sm text-slate-600">
            Vazgeç
          </button>
        )}
        <button
          disabled={busy || !name.trim()}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {submitLabel}
        </button>
      </div>
    </form>
  )
}
