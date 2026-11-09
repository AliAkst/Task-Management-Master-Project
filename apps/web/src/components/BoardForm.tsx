import { useState, type CSSProperties, type FormEvent } from 'react'
import { AlertTriangle } from 'lucide-react'
import { CLOUD_COST_WARNING, useModels } from '../api/assistant'
import type { BoardCreate } from '../lib/types'

export const BACKGROUNDS: { key: NonNullable<BoardCreate['background']>; label: string }[] = [
  { key: 'none', label: 'Yok' },
  { key: 'tint', label: 'Board rengi' },
  { key: 'deniz', label: 'Deniz' },
  { key: 'orman', label: 'Orman' },
  { key: 'gunbatimi', label: 'Gün batımı' },
  { key: 'alacakaranlik', label: 'Alacakaranlık' },
  { key: 'kum', label: 'Kum' },
  { key: 'grafit', label: 'Grafit' },
]

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
  const [background, setBackground] = useState<string>(initial?.background ?? 'none')
  const [modelId, setModelId] = useState(initial?.default_model_id ?? '')
  const models = useModels()
  const all = models.data?.models ?? []
  const chosen = all.find((m) => m.id === modelId)
  const cloudChosen = modelId !== '' && !modelId.startsWith('ollama:')

  function submit(e: FormEvent) {
    e.preventDefault()
    const hours = parseFloat(budgetHours.replace(',', '.'))
    onSubmit({
      name: name.trim(),
      scope_description: scope.trim() || null,
      color,
      weekly_time_budget_min: Number.isFinite(hours) ? Math.round(hours * 60) : null,
      privacy,
      default_model_id: modelId || null,
      background: background as NonNullable<BoardCreate['background']>,
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
      <fieldset className="text-sm">
        <legend className="mb-1 text-slate-600">Arka plan</legend>
        <div className="flex flex-wrap gap-2">
          {BACKGROUNDS.map((bg) => (
            <button
              type="button"
              key={bg.key}
              aria-pressed={background === bg.key}
              onClick={() => setBackground(bg.key)}
              className="flex w-16 flex-col items-center gap-1 text-[12px] text-slate-600"
            >
              <span
                aria-hidden
                data-bg={bg.key}
                style={{ '--board-color': color } as CSSProperties}
                className={`board-bg block h-9 w-full rounded-md border border-slate-300 ${
                  background === bg.key ? 'ring-2 ring-slate-900 ring-offset-2 ring-offset-surface' : ''
                }`}
              />
              {bg.label}
            </button>
          ))}
        </div>
      </fieldset>
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
            onChange={(e) => {
              const v = e.target.value as typeof privacy
              setPrivacy(v)
              // "Sadece local" board bulut modelle calisamaz
              if (v === 'local_only' && cloudChosen) setModelId('')
            }}
          >
            <option value="cloud_allowed">Tüm modeller görebilir</option>
            <option value="local_only">Sadece local model</option>
          </select>
        </label>
      </div>
      <label className="block space-y-1 text-sm">
        <span className="text-slate-600">Bu board'da asistan modeli</span>
        <select
          className="w-full rounded-md border border-slate-300 px-3 py-2"
          value={modelId}
          onChange={(e) => setModelId(e.target.value)}
        >
          <option value="">Varsayılan local model</option>
          <optgroup label="Local">
            {all.filter((m) => m.is_local).map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
          </optgroup>
          {all.some((m) => !m.is_local) && (
            <optgroup label={privacy === 'local_only' ? 'Bulut (bu board sadece local)' : 'Bulut (ücretli)'}>
              {all.filter((m) => !m.is_local).map((m) => (
                <option key={m.id} value={m.id} disabled={privacy === 'local_only'}>{m.label}</option>
              ))}
            </optgroup>
          )}
          {modelId && !chosen && <option value={modelId}>{modelId} (artık listede yok)</option>}
        </select>
        {cloudChosen && (
          <span className="flex gap-1.5 text-[13px] text-amber-900">
            <AlertTriangle size={14} className="mt-0.5 shrink-0" aria-hidden />
            {CLOUD_COST_WARNING} Bu board açıkken asistan otomatik olarak bu modeli kullanır.
          </span>
        )}
      </label>
      <div className="flex justify-end gap-2">
        {onCancel && (
          <button type="button" onClick={onCancel} className="px-3 py-2 text-sm text-slate-600">
            Vazgeç
          </button>
        )}
        <button
          disabled={busy || !name.trim()}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-on-ink disabled:opacity-50"
        >
          {submitLabel}
        </button>
      </div>
    </form>
  )
}
