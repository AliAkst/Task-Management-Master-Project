import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Copy, KeyRound, Loader2 } from 'lucide-react'
import { api } from '../lib/api'
import { Section } from './Page'

interface McpConfig {
  uv: string
  assistant_dir: string
}

interface CreatedToken {
  id: number
  name: string
  token: string
}

/** Yapılandırma blokları: Claude Desktop JSON'u ve Claude Code komutu (anahtar yalnız bu oturumda bellekte). */
export function desktopConfig(cfg: McpConfig, token: string): string {
  return JSON.stringify(
    {
      ajanda: {
        command: cfg.uv,
        args: ['run', '--directory', cfg.assistant_dir, 'python', '-m', 'app.mcp_server'],
        env: { AJANDA_TOKEN: token },
      },
    },
    null,
    2,
  )
}

export function codeCommand(cfg: McpConfig, token: string): string {
  return `claude mcp add ajanda --env AJANDA_TOKEN=${token} -- "${cfg.uv}" run --directory "${cfg.assistant_dir}" python -m app.mcp_server`
}

function CodeBlock({ label, text }: { label: string; text: string }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
    } catch {
      setCopied(false) // pano izni yok: metin seçilip elle kopyalanır
    }
  }
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">{label}</span>
        <button
          type="button"
          onClick={copy}
          aria-label={`${label} yapılandırmasını kopyala`}
          className="inline-flex items-center gap-1.5 rounded-md bg-slate-700 px-2.5 py-1 text-xs text-on-ink"
        >
          {copied ? <Check size={13} aria-hidden /> : <Copy size={13} aria-hidden />}
          {copied ? 'Kopyalandı' : 'Kopyala'}
        </button>
      </div>
      <pre className="overflow-x-auto rounded-md border border-slate-300 bg-surface p-2 font-mono text-xs text-slate-900">{text}</pre>
    </div>
  )
}

/** Ayarlar → Claude bağlantısı: Claude Desktop / Claude Code için anahtar üretir ve yapılandırmayı gösterir. */
export default function ClaudeConnectSettings() {
  const qc = useQueryClient()
  const [created, setCreated] = useState<CreatedToken | null>(null)
  const config = useQuery({
    queryKey: ['assistant', 'mcp-config'],
    queryFn: () => api<McpConfig>('/assistant/mcp/config'),
    retry: false,
    staleTime: 5 * 60_000,
  })
  const create = useMutation({
    mutationFn: () =>
      api<CreatedToken>('/auth/tokens', {
        method: 'POST',
        body: JSON.stringify({ name: 'Claude', scopes: ['read', 'write'] }),
      }),
    onSuccess: (t) => {
      setCreated(t)
      qc.invalidateQueries({ queryKey: ['api-tokens'] })
    },
  })

  return (
    <section id="claude" className="scroll-mt-6">
      <Section
        title="Claude bağlantısı"
        description="Claude Desktop ya da Claude Code bu anahtarla Ajanda'yı kullanır; ücret yok, aboneliğin yeterli. Gizli (local_only) board'lar Claude'a gösterilmez. Onay gerektiren işlemler burada 'Bekleyen işlemler'de onaylanır."
      >
        <button
          type="button"
          disabled={create.isPending || config.isLoading}
          onClick={() => create.mutate()}
          className="inline-flex items-center gap-1.5 rounded-md bg-slate-700 px-3 py-1.5 text-sm text-on-ink disabled:opacity-50"
        >
          {create.isPending ? <Loader2 size={14} className="animate-spin" aria-hidden /> : <KeyRound size={14} aria-hidden />}
          Anahtar üret
        </button>
        {create.isError && <p className="pt-2 text-sm text-red-600">{(create.error as Error).message}</p>}
        {config.isError && (
          <p className="pt-2 text-sm text-red-600">Asistan servisine ulaşılamadı; yapılandırma yolları alınamadı.</p>
        )}

        {created && config.data && (
          <div className="mt-4 space-y-3 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
            <p className="font-semibold">“{created.name}” anahtarı oluşturuldu</p>
            <p>Bu anahtar bir daha gösterilmeyecek; yapılandırmayı şimdi kopyala. Sayfayı yenilersen yalnız “Erişim anahtarları” listesinde ipucu kalır.</p>
            <CodeBlock label="Claude Desktop (claude_desktop_config.json → mcpServers)" text={desktopConfig(config.data, created.token)} />
            <CodeBlock label="Claude Code" text={codeCommand(config.data, created.token)} />
            <button type="button" onClick={() => setCreated(null)} className="underline">
              Kopyaladım, kapat
            </button>
          </div>
        )}
      </Section>
    </section>
  )
}
