import { useEffect, useRef, useState, type FormEvent } from 'react'
import Markdown from 'react-markdown'
import { useQueryClient } from '@tanstack/react-query'
import {
  assistantKeys,
  deleteConversation,
  streamChat,
  TOOL_LABEL,
  useConversations,
  useMessages,
  useModels,
  type AiAction,
  type ChatMessage,
} from '../api/assistant'
import { AlertTriangle, ChevronDown, Loader2, Lock, Search, Sparkles } from 'lucide-react'
import ActionCard from './ActionCard'
import { useAssistantUi } from '../stores/assistant'

interface LiveTurn {
  user: string
  text: string
  tools: { id: string; name: string; done: boolean; ok: boolean }[]
  actions: AiAction[]
  notice?: string
  error?: string
}

const SUGGESTIONS = [
  'Bugün neler planlı?',
  'Son 7 günüm nasıl geçti?',
  'Yarın için gerçekçi bir plan öner',
  'En çok neleri erteliyorum?',
]

function ToolChips({ names }: { names: string[] }) {
  if (names.length === 0) return null
  return (
    <div className="mb-1 flex flex-wrap gap-1">
      {names.map((n, i) => (
        <span key={i} className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-500">
          <Search size={11} className="mr-1 inline align-[-1px]" aria-hidden />
          {TOOL_LABEL[n] ?? n}
        </span>
      ))}
    </div>
  )
}

function Actions({ items }: { items: AiAction[] }) {
  if (items.length === 0) return null
  return (
    <div className="mt-1.5 space-y-1.5">
      {items.map((a) => (
        <ActionCard key={a.id} action={a} />
      ))}
    </div>
  )
}

function Bubble({
  m,
}: {
  m: Pick<ChatMessage, 'role' | 'content'> & { tools?: string[]; actions?: AiAction[] }
}) {
  if (m.role === 'user') {
    return (
      <div className="ml-10 rounded-2xl rounded-br-sm bg-slate-900 px-3 py-2 text-sm whitespace-pre-wrap text-white">
        {m.content}
      </div>
    )
  }
  return (
    <div className="mr-6">
      <ToolChips names={m.tools ?? []} />
      {m.content && (
        <div className="rounded-2xl rounded-bl-sm bg-white px-3 py-2 text-sm ring-1 ring-slate-200 [&_li]:ml-4 [&_ol]:list-decimal [&_p+p]:mt-2 [&_ul]:list-disc">
          <Markdown>{m.content}</Markdown>
        </div>
      )}
      <Actions items={m.actions ?? []} />
    </div>
  )
}

/** Gecmis mesajlari arac turlariyla birlikte tek "asistan cevabi"na toplar. */
type Grouped = ChatMessage & { tools: string[]; actions: AiAction[] }

function groupHistory(msgs: ChatMessage[]): Grouped[] {
  const out: Grouped[] = []
  let tools: string[] = []
  let actions: AiAction[] = []
  for (const m of msgs) {
    if (m.role === 'assistant' && m.tools.length > 0 && !m.content) {
      tools.push(...m.tools)
      actions.push(...(m.actions ?? []))
      continue
    }
    if (m.role === 'assistant') {
      out.push({ ...m, tools: [...tools, ...m.tools], actions: [...actions, ...(m.actions ?? [])] })
      tools = []
      actions = []
    } else {
      out.push({ ...m, tools: [], actions: [] })
    }
  }
  // Cevap metni gelmeden biten tur (or. hata): islemler yine gorunsun
  if (actions.length > 0) out.push({ id: 'pending', role: 'assistant', content: null, tools, actions })
  return out
}

export default function AssistantPanel() {
  const qc = useQueryClient()
  const { open, setOpen, conversationId, setConversation, modelId, setModel } = useAssistantUi()
  const models = useModels()
  const conversations = useConversations()
  const history = useMessages(conversationId)
  const [input, setInput] = useState('')
  const [live, setLive] = useState<LiveTurn | null>(null)
  const [showList, setShowList] = useState(false)
  const abort = useRef<AbortController | null>(null)
  const bottom = useRef<HTMLDivElement>(null)

  const effectiveModel = modelId ?? models.data?.default ?? null
  const current = models.data?.models.find((m) => m.id === effectiveModel)
  const busy = live !== null && !live.error

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: 'end' })
  }, [history.data, live])

  // Profil sayfasindaki "Tanışma sohbetini başlat" gibi disaridan baslatilan sohbet
  const pending = useAssistantUi((s) => s.pendingMessage)
  useEffect(() => {
    if (!open || !pending || busy || !effectiveModel) return
    const message = useAssistantUi.getState().takePendingMessage()
    if (message) {
      setLive(null)
      void send(message)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, pending, effectiveModel])

  if (!open) return null

  async function send(text: string) {
    const message = text.trim()
    if (!message || busy) return
    setInput('')
    const turn: LiveTurn = { user: message, text: '', tools: [], actions: [] }
    setLive(turn)
    const controller = new AbortController()
    abort.current = controller
    let convId = conversationId
    try {
      await streamChat(
        { message, conversation_id: conversationId, model_id: effectiveModel },
        (e) => {
          setLive((t) => {
            if (!t) return t
            switch (e.event) {
              case 'start':
                convId = e.data.conversation_id
                return e.data.dropped_local_messages > 0
                  ? { ...t, notice: `Gizlilik: local modelle yapılan ${e.data.dropped_local_messages} önceki mesaj bu bulut modele gönderilmedi.` }
                  : t
              case 'token':
                return { ...t, text: t.text + e.data.text }
              case 'tool_start':
                return { ...t, tools: [...t.tools, { id: e.data.id, name: e.data.name, done: false, ok: true }] }
              case 'tool_end':
                return { ...t, tools: t.tools.map((x) => (x.id === e.data.id ? { ...x, done: true, ok: e.data.ok } : x)) }
              case 'action':
                return { ...t, actions: [...t.actions, e.data] }
              case 'error':
                return { ...t, error: e.data.message }
              default:
                return t
            }
          })
        },
        controller.signal,
      )
    } catch (err) {
      if (!controller.signal.aborted) {
        setLive((t) => (t ? { ...t, error: (err as Error).message } : t))
        return
      }
    } finally {
      abort.current = null
    }
    if (convId !== null && convId !== conversationId) setConversation(convId)
    // Otomatik yapilan islemler varsa kanban/takvim/plan verisini tazele
    for (const key of [['board'], ['boards'], ['card'], ['calendar'], ['day']]) {
      qc.invalidateQueries({ queryKey: key })
    }
    await Promise.all([
      qc.invalidateQueries({ queryKey: assistantKeys.conversations }),
      convId !== null && qc.invalidateQueries({ queryKey: assistantKeys.messages(convId) }),
    ])
    setLive((t) => (t?.error ? t : null))
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    void send(input)
  }

  const msgs = groupHistory(history.data ?? [])
  const empty = msgs.length === 0 && !live

  return (
    <aside className="flex w-full max-w-md shrink-0 flex-col border-l border-slate-200 bg-slate-50">
      <header className="flex items-center gap-2 border-b border-slate-200 bg-white px-3 py-2">
        <button onClick={() => setShowList((s) => !s)} className="min-w-0 flex-1 truncate text-left text-sm font-medium hover:underline" title="Sohbetler">
          <Sparkles size={15} className="mr-1.5 inline align-[-2px]" aria-hidden />
          {conversations.data?.find((c) => c.id === conversationId)?.title ?? 'Yeni sohbet'}
          <ChevronDown size={14} className="ml-1 inline align-[-2px] text-slate-400" aria-hidden />
        </button>
        <button onClick={() => { setConversation(null); setLive(null); setShowList(false) }} className="rounded px-2 py-1 text-xs text-slate-600 hover:bg-slate-100" title="Yeni sohbet">
          + Yeni
        </button>
        <button onClick={() => setOpen(false)} className="text-lg text-slate-400 hover:text-slate-700" aria-label="Kapat">×</button>
      </header>

      {showList && (
        <ul className="max-h-60 overflow-y-auto border-b border-slate-200 bg-white text-sm">
          {(conversations.data ?? []).length === 0 && <li className="px-3 py-2 text-slate-400">Henüz sohbet yok.</li>}
          {conversations.data?.map((c) => (
            <li key={c.id} className={`group flex items-center gap-2 px-3 py-1.5 hover:bg-slate-50 ${c.id === conversationId ? 'bg-slate-100' : ''}`}>
              <button className="flex-1 truncate text-left" onClick={() => { setConversation(c.id); setLive(null); setShowList(false) }}>{c.title}</button>
              <button
                className="text-xs text-slate-400 opacity-0 group-hover:opacity-100 hover:text-red-600"
                onClick={async () => {
                  await deleteConversation(c.id)
                  if (c.id === conversationId) setConversation(null)
                  qc.invalidateQueries({ queryKey: assistantKeys.conversations })
                }}
              >
                Sil
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
        {empty && (
          <div className="mt-6 text-center text-sm text-slate-500">
            <p className="mb-3">Board'larına, takvimine, planlarına ve istatistiklerine bakarak yardım edebilirim.</p>
            <div className="flex flex-wrap justify-center gap-1.5">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => void send(s)} className="rounded-full bg-white px-3 py-1 text-xs ring-1 ring-slate-200 hover:ring-slate-400">{s}</button>
              ))}
            </div>
            <p className="mt-4 text-xs text-slate-400">Kart, etkinlik ve plan önerebilirim; ne otomatik yapılacağına Ayarlar'dan sen karar verirsin.</p>
          </div>
        )}
        {msgs.map((m) => <Bubble key={m.id} m={m} />)}
        {live && (
          <>
            <Bubble m={{ role: 'user', content: live.user }} />
            {live.notice && <p className="flex gap-1.5 rounded-md bg-amber-50 px-2 py-1 text-xs text-amber-800"><Lock size={12} className="mt-0.5 shrink-0" aria-hidden />{live.notice}</p>}
            <div className="mr-6">
              {live.tools.length > 0 && (
                <div className="mb-1 flex flex-wrap gap-1">
                  {live.tools.map((t) => (
                    <span key={t.id} className={`rounded-full px-2 py-0.5 text-[11px] ${t.done ? (t.ok ? 'bg-slate-100 text-slate-500' : 'bg-red-50 text-red-600') : 'animate-pulse bg-blue-50 text-blue-700'}`}>
                      {t.done ? (
                        t.ok ? <Search size={11} className="mr-1 inline align-[-1px]" aria-hidden /> : <AlertTriangle size={11} className="mr-1 inline align-[-1px]" aria-hidden />
                      ) : (
                        <Loader2 size={11} className="mr-1 inline animate-spin align-[-1px]" aria-hidden />
                      )}
                      {TOOL_LABEL[t.name] ?? t.name}
                    </span>
                  ))}
                </div>
              )}
              {live.text ? (
                <div className="rounded-2xl rounded-bl-sm bg-white px-3 py-2 text-sm ring-1 ring-slate-200 [&_li]:ml-4 [&_ol]:list-decimal [&_ul]:list-disc">
                  <Markdown>{live.text}</Markdown>
                </div>
              ) : (
                !live.error && <p className="text-xs text-slate-400">{current?.is_local ? 'Local model düşünüyor… (ilk mesajda model belleğe yükleniyor)' : 'Düşünüyor…'}</p>
              )}
              <Actions items={live.actions} />
              {live.error && <p className="mt-1 rounded-md bg-red-50 px-2 py-1 text-xs text-red-700">{live.error}</p>}
            </div>
          </>
        )}
        <div ref={bottom} />
      </div>

      <form onSubmit={onSubmit} className="border-t border-slate-200 bg-white p-2">
        <textarea
          rows={2}
          className="w-full resize-none rounded-lg border border-slate-300 px-3 py-2 text-sm"
          placeholder="Asistana yaz… (Enter: gönder, Shift+Enter: yeni satır)"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              void send(input)
            }
          }}
        />
        <div className="mt-1 flex items-center gap-2">
          <select
            className="min-w-0 flex-1 rounded border border-slate-200 bg-white px-1 py-1 text-xs"
            value={effectiveModel ?? ''}
            onChange={(e) => setModel(e.target.value || null)}
            title="Bu mesaj için model"
          >
            {models.data?.models.map((m) => (
              <option key={m.id} value={m.id}>{m.label}{m.is_local ? '' : ' — bulut'}</option>
            ))}
            {models.data && models.data.models.length === 0 && <option value="">Model yok (Ollama çalışıyor mu?)</option>}
          </select>
          {busy ? (
            <button type="button" onClick={() => abort.current?.abort()} className="rounded-md bg-slate-200 px-3 py-1 text-sm">■ Durdur</button>
          ) : (
            <button disabled={!input.trim() || !effectiveModel} className="rounded-md bg-slate-900 px-3 py-1 text-sm text-white disabled:opacity-40">Gönder</button>
          )}
        </div>
        {current && !current.is_local && (
          <p className="mt-1 text-[11px] text-slate-500">Bulut modeli: “sadece local” alanların verisi gönderilmez.</p>
        )}
      </form>
    </aside>
  )
}
