import { useEffect, useRef, useState, type FormEvent } from 'react'
import MarkdownView from './MarkdownView'
import { useQueryClient } from '@tanstack/react-query'
import { useMatch, useSearchParams } from 'react-router-dom'
import { useBoards, useCard } from '../api/boards'
import {
  assistantKeys,
  CLOUD_COST_WARNING,
  deleteConversation,
  streamChat,
  TOOL_LABEL,
  useConversations,
  useMessages,
  useModels,
  type AiAction,
  type ChatMessage,
} from '../api/assistant'
import { AlertTriangle, ChevronDown, Loader2, Lock, Search, Sparkles, X } from 'lucide-react'
import ActionCard from './ActionCard'
import { DictationStatus, useMic } from './MicButton'
import { insertDictated } from '../lib/dictation'
import { usePrefs } from '../stores/prefs'
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
      <div className="ml-10 rounded-2xl rounded-br-sm bg-slate-900 px-3 py-2 text-sm whitespace-pre-wrap text-on-ink">
        {m.content}
      </div>
    )
  }
  return (
    <div className="mr-6">
      <ToolChips names={m.tools ?? []} />
      {m.content && (
        <div className="rounded-2xl rounded-bl-sm bg-surface px-3 py-2 text-sm ring-1 ring-slate-200 [&_li]:ml-4 [&_ol]:list-decimal [&_p+p]:mt-2 [&_ul]:list-disc">
          <MarkdownView content={m.content} />
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

  // Sesli dikte: metin imlec konumuna eklenir; "bitince gonder" aciksa durunca gonderilir
  const inputEl = useRef<HTMLTextAreaElement>(null)
  const inputRef = useRef(input)
  inputRef.current = input
  const dictated = useRef(false)
  const autoSend = usePrefs((s) => s.dictationAutoSend)
  const mic = useMic((text) => {
    const el = inputEl.current
    const r = insertDictated(inputRef.current, el?.selectionStart ?? null, el?.selectionEnd ?? null, text)
    inputRef.current = r.value
    dictated.current = true
    setInput(r.value)
    requestAnimationFrame(() => {
      el?.focus()
      el?.setSelectionRange(r.caret, r.caret)
    })
  })
  const listening = mic.dictation.listening
  useEffect(() => {
    if (listening || !dictated.current) return
    dictated.current = false
    if (autoSend && inputRef.current.trim()) void send(inputRef.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listening])

  // Acik board (varsa): varsayilan modeli "Otomatik" secimini belirler
  const boardMatch = useMatch('/boards/:boardId')
  const boardId = boardMatch ? Number(boardMatch.params.boardId) : null
  // Acik kart penceresi (?card=<id>): "bu kart" baglami; cipteki X ile kapatilir
  const [searchParams] = useSearchParams()
  const rawCard = searchParams.get('card')
  const openCardId = boardId !== null && rawCard && /^\d+$/.test(rawCard) ? Number(rawCard) : null
  const [dismissedCard, setDismissedCard] = useState<number | null>(null)
  const contextCardId = openCardId !== null && dismissedCard !== openCardId ? openCardId : null
  const contextCard = useCard(contextCardId)
  const boards = useBoards()
  const board = boardId !== null ? boards.data?.find((b) => b.id === boardId) : undefined
  const list = models.data?.models ?? []
  const boardDefault =
    board?.default_model_id && list.some((m) => m.id === board.default_model_id) &&
    !(board.privacy === 'local_only' && !board.default_model_id.startsWith('ollama:'))
      ? board.default_model_id
      : null
  const autoModel = boardDefault ?? models.data?.default ?? null
  // Secili model artik listede yoksa (or. saglayici kaldirildi) otomatige don
  const manual = modelId && (!models.data || list.some((m) => m.id === modelId)) ? modelId : null
  const effectiveModel = manual ?? autoModel
  const current = list.find((m) => m.id === effectiveModel)
  const autoLabel = list.find((m) => m.id === autoModel)?.label ?? autoModel?.replace('ollama:', '') ?? 'model yok'
  // Bulut modele gecis onay bekliyor (ucret uyarisi)
  const [pendingCloud, setPendingCloud] = useState<string | null>(null)
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
        { message, conversation_id: conversationId, model_id: manual, board_id: boardId, card_id: contextCardId },
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
      <header className="flex items-center gap-2 border-b border-slate-200 bg-surface px-3 py-2">
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
        <ul className="max-h-60 overflow-y-auto border-b border-slate-200 bg-surface text-sm">
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
                <button key={s} onClick={() => void send(s)} className="rounded-full bg-surface px-3 py-1 text-xs ring-1 ring-slate-200 hover:ring-slate-400">{s}</button>
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
                <div className="rounded-2xl rounded-bl-sm bg-surface px-3 py-2 text-sm ring-1 ring-slate-200 [&_li]:ml-4 [&_ol]:list-decimal [&_ul]:list-disc">
                  <MarkdownView content={live.text} />
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

      <form onSubmit={onSubmit} className="border-t border-slate-200 bg-surface p-2">
        {contextCardId !== null && (
          <div className="mb-1.5 flex items-center gap-1 rounded-full bg-indigo-50 py-0.5 pl-2.5 pr-1 text-[11px] text-indigo-700">
            <span className="min-w-0 flex-1 truncate">
              BaÄŸlam: Â«{contextCard.data?.title ?? `#${contextCardId}`}Â»
            </span>
            <button
              type="button"
              aria-label="Kart baÄŸlamÄ±nÄ± gÃ¶nderme"
              title="Bu mesajda kart baÄŸlamÄ±nÄ± gÃ¶nderme"
              className="rounded-full p-0.5 hover:bg-indigo-100"
              onClick={() => setDismissedCard(contextCardId)}
            >
              <X size={12} aria-hidden />
            </button>
          </div>
        )}
        <textarea
          ref={inputEl}
          rows={2}
          className="w-full resize-none rounded-lg border border-slate-300 px-3 py-2 text-sm"
          placeholder="Asistana yaz… (Enter: gönder, Shift+Enter: yeni satır)"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            mic.onKey(e)
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              void send(input)
            }
          }}
        />
        <DictationStatus mic={mic} className="mt-1 px-1" />
        <div className="mt-1 flex items-center gap-2">
          {mic.button}
          <select
            className="min-w-0 flex-1 rounded border border-slate-200 bg-surface px-1 py-1 text-xs"
            value={manual ?? ''}
            onChange={(e) => {
              const id = e.target.value
              const m = list.find((x) => x.id === id)
              if (m && !m.is_local) setPendingCloud(id)
              else {
                setPendingCloud(null)
                setModel(id || null)
              }
            }}
            title="Bu sohbetteki model"
            aria-label="Model"
          >
            <option value="">
              {boardDefault ? `Otomatik, board'un modeli: ${autoLabel}` : `Otomatik: ${autoLabel}`}
            </option>
            <optgroup label="Local (bilgisayarında)">
              {list.filter((m) => m.is_local).map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
            </optgroup>
            {list.some((m) => !m.is_local) && (
              <optgroup label="Bulut (ücretli)">
                {list.filter((m) => !m.is_local).map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
              </optgroup>
            )}
          </select>
          {busy ? (
            <button type="button" onClick={() => abort.current?.abort()} className="rounded-md bg-slate-200 px-3 py-1 text-sm">■ Durdur</button>
          ) : (
            <button disabled={!input.trim() || !effectiveModel} className="rounded-md bg-slate-900 px-3 py-1 text-sm text-on-ink disabled:opacity-40">Gönder</button>
          )}
        </div>
        {pendingCloud && (
          <div role="alertdialog" aria-label="Bulut modeline geçiş" className="mt-2 rounded-md border border-amber-300 bg-amber-50 p-2 text-xs text-amber-950">
            <p className="flex gap-1.5">
              <AlertTriangle size={14} className="mt-0.5 shrink-0" aria-hidden />
              <span>
                <b>{list.find((m) => m.id === pendingCloud)?.label}</b>. {CLOUD_COST_WARNING}
              </span>
            </p>
            <div className="mt-2 flex justify-end gap-2">
              <button type="button" onClick={() => setPendingCloud(null)} className="px-2 py-1 text-amber-900">Vazgeç</button>
              <button
                type="button"
                autoFocus
                onClick={() => { setModel(pendingCloud); setPendingCloud(null) }}
                className="rounded bg-slate-900 px-2.5 py-1 font-medium text-on-ink"
              >
                Bulut modele geç
              </button>
            </div>
          </div>
        )}
        {current && !current.is_local && !pendingCloud && (
          <p className="mt-1 text-[11px] text-amber-900">
            Ücretli bulut modeli kullanılıyor. “Sadece local” alanların verisi gönderilmez.
          </p>
        )}
        {models.data && list.length === 0 && (
          <p className="mt-1 text-[11px] text-red-700">Kullanılabilir model yok: Ollama çalışıyor mu?</p>
        )}
      </form>
    </aside>
  )
}
