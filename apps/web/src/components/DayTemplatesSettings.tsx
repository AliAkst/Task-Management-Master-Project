import { useState, type FormEvent } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { useDayTemplateMutations, useDayTemplates, type DayTemplate, type TemplateBlock } from '../api/dayTemplates'

const DAYS = ['Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt', 'Paz']
const KINDS: { value: TemplateBlock['kind']; label: string }[] = [
  { value: 'yol', label: 'Yol' },
  { value: 'mesai', label: 'Mesai' },
  { value: 'yemek', label: 'Yemek' },
  { value: 'rutin', label: 'Rutin' },
  { value: 'diger', label: 'Diğer' },
]
const BUFFERS = [0, 5, 10, 15] as const
const input = 'rounded-md border border-slate-300 bg-surface px-2 py-1.5 text-sm'

interface Form {
  id: number | null
  name: string
  weekdays: number[]
  day_start: string
  day_end: string
  buffer_min: 0 | 5 | 10 | 15
  blocks: TemplateBlock[]
}

// Saat alani gece yarisini "00:00" yazar; sunucu "24:00" ister.
const fromServerEnd = (t: string) => (t === '24:00' ? '00:00' : t)
const toServerEnd = (t: string) => (t === '00:00' ? '24:00' : t)
const hm = (t: string) => t.slice(0, 5)

const EMPTY: Form = { id: null, name: '', weekdays: [], day_start: '08:00', day_end: '23:00', buffer_min: 0, blocks: [] }

// Genel saatler; kisisel saat koda yazilmaz. Hafta gunleri bos birakilir.
const SAMPLES: Record<string, Pick<Form, 'name' | 'blocks'>> = {
  'Ofis günü': {
    name: 'Ofis günü',
    blocks: [
      { title: 'Yol', start: '07:00', end: '09:00', kind: 'yol' },
      { title: 'Mesai', start: '09:00', end: '18:00', kind: 'mesai' },
      { title: 'Yol', start: '18:00', end: '20:00', kind: 'yol' },
    ],
  },
  'Ev günü': {
    name: 'Ev günü',
    blocks: [
      { title: 'Mesai', start: '09:00', end: '12:00', kind: 'mesai' },
      { title: 'Öğle arası', start: '12:00', end: '13:00', kind: 'yemek' },
      { title: 'Mesai', start: '13:00', end: '18:00', kind: 'mesai' },
    ],
  },
}

function toForm(t: DayTemplate): Form {
  return {
    id: t.id,
    name: t.name,
    weekdays: [...t.weekdays],
    day_start: hm(t.day_start),
    day_end: hm(t.day_end),
    buffer_min: t.buffer_min as Form['buffer_min'],
    blocks: t.blocks.map((b) => ({ ...b, end: fromServerEnd(b.end) })),
  }
}

/** Ayarlar → Gün şablonları: "Ofis günü / Ev günü" iskeletleri. */
export default function DayTemplatesSettings() {
  const templates = useDayTemplates()
  const m = useDayTemplateMutations()
  const [form, setForm] = useState<Form | null>(null)
  const [error, setError] = useState<string | null>(null)

  const list = templates.data ?? []
  const taken = new Map<number, string>() // hafta gunu -> baska sablonun adi
  for (const t of list) {
    if (t.id === form?.id) continue
    for (const d of t.weekdays) taken.set(d, t.name)
  }

  const busy = m.create.isPending || m.update.isPending || m.remove.isPending
  const patch = (p: Partial<Form>) => setForm((f) => (f ? { ...f, ...p } : f))
  const patchBlock = (i: number, p: Partial<TemplateBlock>) =>
    setForm((f) => (f ? { ...f, blocks: f.blocks.map((b, j) => (j === i ? { ...b, ...p } : b)) } : f))

  function save(e: FormEvent) {
    e.preventDefault()
    if (!form || busy) return
    setError(null)
    const body = {
      name: form.name.trim(),
      weekdays: form.weekdays,
      day_start: `${form.day_start}:00`,
      day_end: `${form.day_end}:00`,
      buffer_min: form.buffer_min,
      blocks: [...form.blocks]
        .sort((a, b) => a.start.localeCompare(b.start))
        .map((b) => ({ ...b, title: b.title.trim(), end: toServerEnd(b.end) })),
    }
    const opts = { onSuccess: () => setForm(null), onError: (err: Error) => setError(err.message) }
    if (form.id == null) m.create.mutate(body, opts)
    else m.update.mutate({ id: form.id, body }, opts)
  }

  return (
    <section id="sablonlar" className="scroll-mt-6">
      <h2 className="text-[22px]">Gün şablonları</h2>
      <p className="mt-1 mb-2 max-w-prose text-[15px] text-slate-600">
        “Ofis günü” gibi sabit blokları bir kez tanımla; haftanın günlerine bağla. Bugün sayfasında tek tıkla planına girer.
      </p>
      {templates.error && <p className="text-[14px] text-red-700">{templates.error.message}</p>}

      <div className="divide-y divide-slate-200 border-y border-slate-200">
        {list.length === 0 && !templates.isLoading && <p className="py-3 text-[15px] text-slate-500">Henüz şablon yok.</p>}
        {list.map((t) => (
          <div key={t.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
            <div className="min-w-0">
              <p className="font-semibold">{t.name}</p>
              <p className="text-[14px] text-slate-600">
                {t.weekdays.length ? t.weekdays.map((d) => DAYS[d]).join(', ') : 'Hafta günü seçilmemiş'} · {t.blocks.length} blok
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button type="button" onClick={() => { setError(null); setForm(toForm(t)) }} className="rounded-md border border-slate-300 px-3 py-1 text-sm hover:border-slate-900">
                Düzenle
              </button>
              <button
                type="button"
                aria-label={`${t.name} şablonunu sil`}
                disabled={busy}
                onClick={() => { if (window.confirm(`“${t.name}” silinsin mi?`)) m.remove.mutate(t.id) }}
                className="rounded p-1.5 text-slate-500 hover:bg-slate-200 hover:text-red-700 disabled:opacity-50"
              >
                <Trash2 size={16} aria-hidden />
              </button>
            </div>
          </div>
        ))}
      </div>
      {m.remove.error && <p className="mt-1 text-[14px] text-red-700">{m.remove.error.message}</p>}

      {!form && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button type="button" onClick={() => { setError(null); setForm({ ...EMPTY }) }} disabled={list.length >= 10} className="inline-flex items-center gap-1 rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-on-ink disabled:opacity-50">
            <Plus size={15} aria-hidden /> Yeni şablon
          </button>
          <span className="text-[13px] text-slate-500">Örnek ekle:</span>
          {Object.keys(SAMPLES).map((k) => (
            <button key={k} type="button" disabled={list.length >= 10} onClick={() => { setError(null); setForm({ ...EMPTY, ...SAMPLES[k] }) }} className="rounded-md border border-slate-300 px-2.5 py-1 text-sm hover:border-slate-900 disabled:opacity-50">
              {k}
            </button>
          ))}
        </div>
      )}

      {form && (
        <form onSubmit={save} className="mt-4 space-y-4 border border-slate-200 bg-surface p-4">
          <div className="flex flex-wrap items-end gap-4">
            <label className="text-sm">
              <span className="mb-1 block text-slate-600">Ad</span>
              <input className={input} value={form.name} maxLength={60} required onChange={(e) => patch({ name: e.target.value })} />
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-slate-600">Gün başlangıcı</span>
              <input type="time" className={input} value={form.day_start} required onChange={(e) => patch({ day_start: e.target.value })} />
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-slate-600">Gün bitişi</span>
              <input type="time" className={input} value={form.day_end} required onChange={(e) => patch({ day_end: e.target.value })} />
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-slate-600">Tampon (dk)</span>
              <select className={input} value={form.buffer_min} onChange={(e) => patch({ buffer_min: Number(e.target.value) as Form['buffer_min'] })}>
                {BUFFERS.map((b) => <option key={b} value={b}>{b}</option>)}
              </select>
            </label>
          </div>

          <div>
            <span className="mb-1 block text-sm text-slate-600">Hafta günleri</span>
            <div className="flex flex-wrap gap-1.5" role="group" aria-label="Hafta günleri">
              {DAYS.map((label, d) => {
                const other = taken.get(d)
                const on = form.weekdays.includes(d)
                return (
                  <button
                    key={d}
                    type="button"
                    aria-pressed={on}
                    disabled={!!other}
                    title={other ? `${other} şablonunda` : undefined}
                    onClick={() => patch({ weekdays: on ? form.weekdays.filter((x) => x !== d) : [...form.weekdays, d].sort() })}
                    className={`rounded-md border px-2.5 py-1 text-sm disabled:opacity-40 ${on ? 'border-slate-900 bg-slate-900 text-on-ink' : 'border-slate-300 hover:border-slate-900'}`}
                  >
                    {label}
                  </button>
                )
              })}
            </div>
            {taken.size > 0 && <p className="mt-1 text-[13px] text-slate-500">Soluk günler başka bir şablona bağlı.</p>}
          </div>

          <div>
            <span className="mb-1 block text-sm text-slate-600">Bloklar (kaydederken saate göre sıralanır)</span>
            <ul className="space-y-2">
              {form.blocks.map((b, i) => (
                <li key={i} className="flex flex-wrap items-center gap-2">
                  <input className={`${input} w-40`} aria-label="Blok başlığı" value={b.title} maxLength={60} required onChange={(e) => patchBlock(i, { title: e.target.value })} />
                  <input type="time" className={input} aria-label="Blok başlangıcı" value={b.start} required onChange={(e) => patchBlock(i, { start: e.target.value })} />
                  <span aria-hidden>–</span>
                  <input type="time" className={input} aria-label="Blok bitişi" value={b.end} required onChange={(e) => patchBlock(i, { end: e.target.value })} />
                  <select className={input} aria-label="Blok türü" value={b.kind} onChange={(e) => patchBlock(i, { kind: e.target.value as TemplateBlock['kind'] })}>
                    {KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
                  </select>
                  <button type="button" aria-label="Bloğu sil" onClick={() => patch({ blocks: form.blocks.filter((_, j) => j !== i) })} className="rounded p-1.5 text-slate-500 hover:bg-slate-200 hover:text-red-700">
                    <Trash2 size={15} aria-hidden />
                  </button>
                </li>
              ))}
            </ul>
            <button type="button" disabled={form.blocks.length >= 12} onClick={() => patch({ blocks: [...form.blocks, { title: '', start: '09:00', end: '10:00', kind: 'diger' }] })} className="mt-2 inline-flex items-center gap-1 text-sm text-blue-700 hover:underline disabled:opacity-50">
              <Plus size={14} aria-hidden /> Blok ekle
            </button>
          </div>

          {error && <p className="text-[14px] text-red-700">{error}</p>}
          <div className="flex items-center justify-end gap-3">
            <button type="button" onClick={() => setForm(null)} className="text-sm text-slate-600 hover:underline">Vazgeç</button>
            <button type="submit" disabled={busy || form.blocks.length === 0} className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-on-ink disabled:opacity-50">
              {busy ? 'Kaydediliyor…' : 'Kaydet'}
            </button>
          </div>
        </form>
      )}
    </section>
  )
}
