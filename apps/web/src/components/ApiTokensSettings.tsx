import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Copy, KeyRound, Loader2, Trash2 } from 'lucide-react'
import { api } from '../lib/api'
import { formatDateTime } from '../lib/format'
import { Section } from './Page'

interface ApiToken {
  id: number
  name: string
  token_hint: string
  scopes: string[]
  created_at: string
  last_used_at: string | null
  expires_at: string | null
}

interface CreatedToken extends Omit<ApiToken, 'last_used_at'> {
  token: string
}

const KEY = ['api-tokens'] as const
const input = 'rounded-md border border-slate-300 bg-surface px-2 py-1.5 text-sm'

const EXPIRY_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: 'Süresiz' },
  { value: '30', label: '30 gün' },
  { value: '90', label: '90 gün' },
  { value: '365', label: '1 yıl' },
]

function useApiTokens() {
  return useQuery({ queryKey: KEY, queryFn: () => api<ApiToken[]>('/auth/tokens') })
}

/** Ayarlar → Erişim anahtarları: zamanlayıcı ve MCP gibi uzun ömürlü, iptal edilebilir anahtarlar. */
export default function ApiTokensSettings() {
  const qc = useQueryClient()
  const tokens = useApiTokens()
  const [name, setName] = useState('')
  const [canWrite, setCanWrite] = useState(false)
  const [expiry, setExpiry] = useState('')
  const [created, setCreated] = useState<CreatedToken | null>(null)
  const [copied, setCopied] = useState(false)

  const create = useMutation({
    mutationFn: () =>
      api<CreatedToken>('/auth/tokens', {
        method: 'POST',
        body: JSON.stringify({
          name: name.trim(),
          scopes: canWrite ? ['read', 'write'] : ['read'],
          expires_in_days: expiry ? Number(expiry) : null,
        }),
      }),
    onSuccess: (t) => {
      setCreated(t)
      setCopied(false)
      setName('')
      setCanWrite(false)
      setExpiry('')
      qc.invalidateQueries({ queryKey: KEY })
    },
  })

  const revoke = useMutation({
    mutationFn: (id: number) => api<void>(`/auth/tokens/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (!name.trim() || create.isPending) return
    create.mutate()
  }

  const copy = async () => {
    if (!created) return
    try {
      await navigator.clipboard.writeText(created.token)
      setCopied(true)
    } catch {
      setCopied(false) // pano izni yok: alan seçili, elle kopyalanır
    }
  }

  return (
    <section id="anahtarlar" className="scroll-mt-6">
      <Section
        title="Erişim anahtarları"
        description="Arka plandaki hatırlatıcılar ve Claude bağlantısı gibi dış araçlar için anahtar üret. Anahtar yalnızca oluşturulurken bir kez gösterilir; istediğin zaman iptal edebilirsin. Anahtarlar hesap, bağlantı ve dosya ayarlarına erişemez."
      >
        {created && (
          <div className="mb-4 space-y-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
            <p className="font-semibold">“{created.name}” anahtarı oluşturuldu</p>
            <div className="flex flex-wrap items-center gap-2">
              <input
                readOnly
                value={created.token}
                aria-label="Yeni erişim anahtarı"
                onFocus={(e) => e.currentTarget.select()}
                className={`${input} min-w-0 flex-1 font-mono text-xs text-slate-900`}
              />
              <button
                type="button"
                onClick={copy}
                className="inline-flex items-center gap-1.5 rounded-md bg-slate-700 px-3 py-1.5 text-sm text-on-ink"
                aria-label="Anahtarı kopyala"
              >
                {copied ? <Check size={14} aria-hidden /> : <Copy size={14} aria-hidden />}
                {copied ? 'Kopyalandı' : 'Kopyala'}
              </button>
            </div>
            <p>Bu anahtar bir daha gösterilmeyecek. Şimdi kopyalayıp güvenli bir yere kaydet.</p>
            <button type="button" onClick={() => setCreated(null)} className="underline">
              Kopyaladım, kapat
            </button>
          </div>
        )}

        <form onSubmit={submit} className="flex flex-wrap items-end gap-3 pb-4">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-slate-600">Ad</span>
            <input
              value={name}
              maxLength={100}
              onChange={(e) => setName(e.target.value)}
              placeholder="Örn. Claude Desktop"
              className={`${input} w-56`}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-slate-600">Geçerlilik</span>
            <select value={expiry} onChange={(e) => setExpiry(e.target.value)} className={input}>
              {EXPIRY_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2 pb-2 text-sm">
            <input type="checkbox" checked={canWrite} onChange={(e) => setCanWrite(e.target.checked)} />
            Yazma izni
          </label>
          <button
            type="submit"
            disabled={!name.trim() || create.isPending}
            className="inline-flex items-center gap-1.5 rounded-md bg-slate-700 px-3 py-1.5 text-sm text-on-ink disabled:opacity-50"
          >
            {create.isPending ? <Loader2 size={14} className="animate-spin" aria-hidden /> : <KeyRound size={14} aria-hidden />}
            Yeni anahtar
          </button>
        </form>
        {create.isError && <p className="pb-3 text-sm text-red-600">{(create.error as Error).message}</p>}

        {tokens.isLoading ? (
          <p className="text-sm text-slate-500">Yükleniyor…</p>
        ) : (tokens.data ?? []).length === 0 ? (
          <p className="text-sm text-slate-500">Henüz erişim anahtarı yok.</p>
        ) : (
          <ul className="divide-y divide-slate-200 border-y border-slate-200">
            {tokens.data?.map((t) => (
              <li key={t.id} className="flex flex-wrap items-center justify-between gap-x-6 gap-y-1 py-3">
                <div className="min-w-0">
                  <p className="font-semibold">
                    {t.name}{' '}
                    <span className="font-mono text-xs font-normal text-slate-500">{t.token_hint}</span>
                  </p>
                  <p className="text-[13px] text-slate-600">
                    {t.scopes.includes('write') ? 'Okuma + yazma' : 'Yalnız okuma'} · oluşturuldu {formatDateTime(t.created_at)} ·{' '}
                    {t.last_used_at ? `son kullanım ${formatDateTime(t.last_used_at)}` : 'hiç kullanılmadı'}
                    {t.expires_at ? ` · ${formatDateTime(t.expires_at)} tarihinde sona erer` : ''}
                  </p>
                </div>
                <button
                  type="button"
                  disabled={revoke.isPending}
                  onClick={() => {
                    if (window.confirm(`“${t.name}” anahtarı iptal edilsin mi? Bunu kullanan araçlar çalışmayı durdurur.`)) {
                      revoke.mutate(t.id)
                    }
                  }}
                  aria-label={`${t.name} anahtarını iptal et`}
                  className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-sm text-red-700 hover:bg-red-50 disabled:opacity-50"
                >
                  <Trash2 size={14} aria-hidden />
                  İptal et
                </button>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </section>
  )
}
