import { useState, type FormEvent } from 'react'
import { AlertTriangle, Check, ExternalLink, KeyRound, Loader2, Plus, X } from 'lucide-react'
import {
  CLOUD_COST_WARNING,
  useModelPrefs,
  useModels,
  useProviderMutations,
  useProviders,
  useSetDefaultModel,
  type ProviderConfig,
} from '../api/assistant'

/** Kullanicinin varsayilan modeli: sadece local modeller secilebilir. */
function DefaultModel() {
  const models = useModels()
  const prefs = useModelPrefs()
  const set = useSetDefaultModel()
  const local = (models.data?.models ?? []).filter((m) => m.is_local)
  const value = prefs.data?.default_model_id ?? ''

  return (
    <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2 py-4">
      <div className="max-w-prose">
        <p className="font-semibold">Varsayılan model</p>
        <p className="text-[14px] text-slate-600">
          Her sohbet bu modelle başlar ve bilgisayarında çalışır. Bulut modeller ücretli olduğu için varsayılan
          yapılamaz; sohbet panelinden ya da board ayarlarından bilerek seçilir.
        </p>
      </div>
      <select
        className="min-w-56 rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
        value={value}
        disabled={set.isPending || local.length === 0}
        onChange={(e) => set.mutate(e.target.value)}
        aria-label="Varsayılan model"
      >
        {local.length === 0 && <option value={value}>{value ? value.replace('ollama:', '') : 'Local model bulunamadı'}</option>}
        {local.map((m) => (
          <option key={m.id} value={m.id}>{m.label}</option>
        ))}
      </select>
      {local.length === 0 && models.data && (
        <p className="w-full text-[13px] text-slate-500">Ollama kapalı görünüyor; açınca kurulu modellerin burada listelenir.</p>
      )}
      {set.error && <p className="w-full text-[13px] text-red-700">{set.error.message}</p>}
    </div>
  )
}

/** Model adlari: secili olanlar (kaldirilabilir) + oneriler (tikla-ekle) + elle ekleme. */
function ModelPicker({
  value,
  onChange,
  suggestions,
}: {
  value: string[]
  onChange: (v: string[]) => void
  suggestions: string[]
}) {
  const [draft, setDraft] = useState('')
  const [filter, setFilter] = useState('')
  const add = (name: string) => {
    const n = name.trim()
    if (n && !value.includes(n)) onChange([...value, n])
  }
  const rest = suggestions.filter((s) => !value.includes(s) && s.toLowerCase().includes(filter.toLowerCase()))

  return (
    <div className="space-y-2">
      <ul className="flex flex-wrap gap-1.5" aria-label="Kullanılacak modeller">
        {value.length === 0 && <li className="text-[13px] text-slate-500">Henüz model seçilmedi.</li>}
        {value.map((m) => (
          <li key={m} className="inline-flex items-center gap-1 rounded-full bg-slate-900 py-0.5 pr-1 pl-2.5 text-[13px] text-white">
            {m}
            <button type="button" onClick={() => onChange(value.filter((x) => x !== m))} className="rounded-full p-0.5 hover:bg-slate-700" aria-label={`${m} modelini çıkar`}>
              <X size={12} />
            </button>
          </li>
        ))}
      </ul>
      {suggestions.length > 8 && (
        <input
          className="w-full rounded-md border border-slate-300 px-2 py-1 text-[13px]"
          placeholder="Hesabındaki modellerde ara"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      )}
      {rest.length > 0 && (
        <div className="flex max-h-28 flex-wrap gap-1.5 overflow-y-auto">
          {rest.slice(0, 60).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => add(s)}
              className="inline-flex items-center gap-1 rounded-full border border-dashed border-slate-400 px-2.5 py-0.5 text-[13px] text-slate-700 hover:border-slate-900 hover:text-slate-900"
            >
              <Plus size={12} aria-hidden /> {s}
            </button>
          ))}
        </div>
      )}
      <div className="flex gap-1.5">
        <input
          className="min-w-0 flex-1 rounded-md border border-slate-300 px-2 py-1 text-[13px]"
          placeholder="Model adını yaz (sağlayıcının belgelerindeki kimlik)"
          value={draft}
          maxLength={100}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              add(draft)
              setDraft('')
            }
          }}
        />
        <button type="button" onClick={() => { add(draft); setDraft('') }} disabled={!draft.trim()} className="rounded-md border border-slate-300 px-2.5 text-[13px] disabled:opacity-40">
          Ekle
        </button>
      </div>
    </div>
  )
}

function ProviderEditor({ p, onClose }: { p: ProviderConfig; onClose: () => void }) {
  const m = useProviderMutations()
  const [key, setKey] = useState('')
  const [models, setModels] = useState<string[]>(p.connected ? p.models : p.suggested_models.slice(0, 1))
  const [found, setFound] = useState<string[] | null>(null)

  function submit(e: FormEvent) {
    e.preventDefault()
    m.save.mutate(
      { provider: p.provider, data: { api_key: key.trim() || null, models, is_enabled: p.connected ? p.is_enabled : true } },
      { onSuccess: onClose },
    )
  }

  const canSave = (p.connected || key.trim().length > 0) && models.length > 0
  return (
    <form onSubmit={submit} className="mt-3 space-y-4 border-l-2 border-slate-900 pl-4">
      <label className="block space-y-1">
        <span className="flex items-baseline justify-between gap-3 text-[14px] font-semibold">
          API anahtarı
          <a href={p.key_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[13px] font-normal text-blue-700 hover:underline">
            Anahtar al <ExternalLink size={12} aria-hidden />
          </a>
        </span>
        <input
          type="password"
          autoComplete="off"
          spellCheck={false}
          className="w-full rounded-md border border-slate-300 px-3 py-1.5 font-mono text-[13px]"
          placeholder={p.connected ? `Kayıtlı anahtar ${p.key_hint}; değiştirmek için yenisini yapıştır` : 'Anahtarı buraya yapıştır'}
          value={key}
          maxLength={500}
          onChange={(e) => setKey(e.target.value)}
        />
        <span className="block text-[12px] text-slate-500">Şifrelenerek saklanır; bir daha gösterilmez.</span>
      </label>

      <div className="space-y-1">
        <p className="text-[14px] font-semibold">Kullanılacak modeller</p>
        <ModelPicker value={models} onChange={setModels} suggestions={found ?? p.suggested_models} />
        {found && <p className="text-[12px] text-slate-500">Hesabında {found.length} model bulundu; eklemek için tıkla.</p>}
      </div>

      <p className="flex gap-2 text-[13px] text-amber-900">
        <AlertTriangle size={15} className="mt-0.5 shrink-0" aria-hidden />
        {CLOUD_COST_WARNING} Varsayılan model local kalır.
      </p>

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => m.test.mutate({ provider: p.provider, api_key: key.trim() || undefined }, { onSuccess: (r) => setFound(r.models) })}
          disabled={m.test.isPending || (!p.connected && !key.trim())}
          className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-40"
          title="Anahtarı doğrular ve hesabındaki modelleri listeler (ücretsiz, mesaj göndermez)"
        >
          {m.test.isPending ? <Loader2 size={14} className="animate-spin" aria-hidden /> : <KeyRound size={14} aria-hidden />}
          Anahtarı doğrula
        </button>
        {m.test.isSuccess && <span className="inline-flex items-center gap-1 text-[13px] text-green-700"><Check size={14} aria-hidden /> Anahtar geçerli</span>}
        {m.test.error && <span className="text-[13px] text-red-700">{m.test.error.message}</span>}
        <span className="flex-1" />
        <button type="button" onClick={onClose} className="px-2 py-1.5 text-sm text-slate-600">Vazgeç</button>
        <button disabled={!canSave || m.save.isPending} className="rounded-md bg-slate-900 px-4 py-1.5 text-sm font-medium text-white disabled:opacity-40">
          {p.connected ? 'Değişiklikleri kaydet' : 'Bağla'}
        </button>
      </div>
      {m.save.error && <p className="text-[13px] text-red-700">{m.save.error.message}</p>}
    </form>
  )
}

function ProviderRow({ p }: { p: ProviderConfig }) {
  const m = useProviderMutations()
  const [editing, setEditing] = useState(false)
  const status = !p.connected
    ? 'Bağlı değil'
    : p.is_enabled
      ? `Bağlı, anahtar ${p.key_hint}. ${p.models.length} model sohbet panelinde`
      : `Bağlı ama kapalı, anahtar ${p.key_hint}`

  return (
    <li className="py-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="min-w-0 flex-1">
          <p className="font-semibold">{p.label}</p>
          <p className={`text-[14px] ${p.connected && p.is_enabled ? 'text-slate-700' : 'text-slate-500'}`}>{status}</p>
        </div>
        {p.connected && (
          <label className="inline-flex items-center gap-2 text-[14px]">
            <input
              type="checkbox"
              aria-label={`${p.label} modellerini kullan`}
              checked={p.is_enabled}
              disabled={m.save.isPending}
              onChange={(e) => m.save.mutate({ provider: p.provider, data: { models: p.models, is_enabled: e.target.checked } })}
            />
            Kullan
          </label>
        )}
        {!editing && (
          <button onClick={() => setEditing(true)} className="rounded-md border border-slate-300 px-3 py-1 text-sm hover:border-slate-900">
            {p.connected ? 'Düzenle' : 'Bağla'}
          </button>
        )}
        {p.connected && !editing && (
          <button
            onClick={() => confirm(`${p.label} bağlantısı ve kayıtlı anahtar silinsin mi?`) && m.remove.mutate(p.provider)}
            className="text-sm text-slate-500 hover:text-red-700"
          >
            Kaldır
          </button>
        )}
      </div>
      {editing && <ProviderEditor p={p} onClose={() => setEditing(false)} />}
    </li>
  )
}

/** Ayarlar → Asistan modeli: local varsayilan + bulut saglayici baglantilari. */
export default function ModelSettings() {
  const providers = useProviders()
  return (
    <section>
      <h2 className="text-[22px]">Asistan modeli</h2>
      <p className="mt-1 mb-2 max-w-prose text-[15px] text-slate-600">
        Asistanın hangi modelle düşüneceği. Local modeller ücretsizdir ve verin bilgisayarından çıkmaz.
      </p>
      <div className="divide-y divide-slate-200 border-y border-slate-200">
        <DefaultModel />
        <div className="py-4">
          <p className="font-semibold">Bulut modeller</p>
          <p className="max-w-prose text-[14px] text-slate-600">
            Kendi API anahtarınla Claude, GPT ya da Gemini bağlayabilirsin. Bağladığın modeller sohbet panelinde
            “ücretli” etiketiyle görünür. “Sadece local” board'ların verisi bu modellere hiçbir zaman gönderilmez.
          </p>
          {providers.error && <p className="mt-2 text-[14px] text-red-700">{providers.error.message} (asistan servisi çalışıyor mu?)</p>}
          <ul className="divide-y divide-slate-200">{providers.data?.map((p) => <ProviderRow key={p.provider} p={p} />)}</ul>
        </div>
      </div>
    </section>
  )
}
