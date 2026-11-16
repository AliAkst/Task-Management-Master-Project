import { useState, type FormEvent } from 'react'
import {
  CATEGORY_LABELS,
  assistantErrorText,
  useCorrect,
  useDialog,
  type DialogTurn,
} from '../../api/english'
import { DictationStatus, useMic } from '../MicButton'
import { localCorrectEnabled, speak } from '../../lib/speak'
import SpeakButton from './SpeakButton'

const MAX_SENTENCES = 5
const MAX_TURNS = 10
const box = 'w-full rounded-md border border-slate-300 bg-surface px-3 py-2 text-[15px]'

function Corrector() {
  const [text, setText] = useState('')
  const correct = useCorrect()
  // Genel dikte tercihi + ilk kullanim bilgisi MicButton'da (T5-D1); dil Ingilizce
  const mic = useMic(
    (t) => setText((cur) => (cur.trim() ? `${cur.replace(/\s+$/, '')}\n${t}` : t)),
    'en-US',
  )
  const dictation = mic.dictation

  const lines = text
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
  const tooMany = lines.length > MAX_SENTENCES
  const pending = correct.isPending

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (pending || lines.length === 0 || tooMany) return
    if (dictation.listening) dictation.stop()
    correct.mutate(lines)
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <label className="block">
        <span className="mb-1 block text-sm font-semibold">1–5 cümle, her satıra bir cümle</span>
        <textarea
          rows={4}
          className={box}
          value={text}
          readOnly={pending}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={mic.onKey}
          placeholder="I goes to school yesterday."
        />
      </label>
      {tooMany && (
        <p role="alert" className="text-sm text-red-700">
          En fazla {MAX_SENTENCES} cümle.
        </p>
      )}
      <div className="flex flex-wrap items-center gap-3">
        {mic.button}
        <button
          disabled={pending || lines.length === 0 || tooMany}
          className="rounded-md bg-slate-900 px-4 py-1.5 text-[15px] text-on-ink disabled:opacity-40"
        >
          Düzelt
        </button>
        {pending && <span className="text-sm text-slate-600">Model düşünüyor…</span>}
      </div>
      <DictationStatus mic={mic} />

      {correct.isError && (
        <p role="alert" className="text-sm text-red-700">
          {assistantErrorText(correct.error)}
        </p>
      )}
      {correct.data && (
        <div className="space-y-3 pt-2">
          {correct.data.pending_action_id != null && (
            <p className="text-sm text-slate-600">Hata kayıtları onayını bekliyor (Asistan → bekleyen işlemler).</p>
          )}
          {correct.data.save_error && <p className="text-sm text-red-700">Hatalar kaydedilemedi: {correct.data.save_error}</p>}
          <ul className="space-y-3">
            {correct.data.results.map((r, i) => (
              <li key={i} className="rounded-xl border border-slate-200 bg-surface p-4">
                <p className="text-[15px] text-slate-600">{r.original}</p>
                {r.ok === null ? (
                  <p className="mt-1 text-sm text-slate-500">değerlendirilemedi</p>
                ) : (
                  <p className="mt-1 flex items-center gap-1 text-[16px] font-semibold">
                    {r.corrected}
                    <SpeakButton text={r.corrected} label="Düzeltilmiş cümleyi seslendir" />
                  </p>
                )}
                {r.ok === true && <p className="text-sm text-slate-600">Doğru.</p>}
                {r.mistakes.length > 0 && (
                  <ul className="mt-2 space-y-1.5">
                    {r.mistakes.map((m, j) => (
                      <li key={j} className="text-sm">
                        <span className="mr-2 rounded-full border border-slate-300 px-2 py-0.5 text-xs">
                          {CATEGORY_LABELS[m.category] ?? m.category}
                        </span>
                        {m.original} → {m.corrected}
                        {m.explanation_tr && <span className="block text-slate-600">{m.explanation_tr}</span>}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </form>
  )
}

function Dialog() {
  const [history, setHistory] = useState<DialogTurn[]>([])
  const [input, setInput] = useState('')
  const [autoSpeak, setAutoSpeak] = useState(false)
  const dialog = useDialog()
  const userTurns = history.filter((t) => t.role === 'user').length
  const full = userTurns >= MAX_TURNS

  const send = (e: FormEvent) => {
    e.preventDefault()
    const t = input.trim()
    if (!t || dialog.isPending || full) return
    dialog.mutate(
      { history, user_text: t },
      {
        onSuccess: (res) => {
          setHistory((h) => [...h, { role: 'user', text: t }, { role: 'coach', text: res.reply }])
          setInput('')
          if (autoSpeak) speak(res.reply)
        },
      },
    )
  }

  return (
    <div className="space-y-3">
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={autoSpeak} onChange={(e) => setAutoSpeak(e.target.checked)} />
        Koç cevabını otomatik seslendir
      </label>
      {history.length > 0 && (
        <ul className="space-y-2">
          {history.map((t, i) => (
            <li
              key={i}
              className={`max-w-[85%] rounded-2xl px-3 py-2 text-[15px] ${
                t.role === 'user' ? 'ml-auto bg-slate-900 text-on-ink' : 'border border-slate-200 bg-surface'
              }`}
            >
              {t.text}
              {t.role === 'coach' && <SpeakButton text={t.text} label="Koç cevabını seslendir" />}
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={send} className="flex gap-2">
        <input
          className={box}
          value={input}
          readOnly={dialog.isPending}
          onChange={(e) => setInput(e.target.value)}
          placeholder={full ? 'Diyalog doldu (10 tur)' : 'Say something in English…'}
          aria-label="Diyalog mesajı"
          disabled={full}
        />
        <button
          disabled={dialog.isPending || full || !input.trim()}
          className="rounded-md bg-slate-900 px-4 py-1.5 text-[15px] text-on-ink disabled:opacity-40"
        >
          Gönder
        </button>
      </form>
      {dialog.isPending && <p className="text-sm text-slate-600">Model düşünüyor…</p>}
      {dialog.isError && (
        <p role="alert" className="text-sm text-red-700">
          {assistantErrorText(dialog.error)}
        </p>
      )}
      {history.length > 0 && (
        <button
          onClick={() => setHistory([])}
          className="text-sm text-slate-600 underline"
          type="button"
        >
          Diyaloğu sıfırla
        </button>
      )}
    </div>
  )
}

export default function PracticeTab() {
  const local = localCorrectEnabled()
  return (
    <div className="space-y-10">
      <section aria-label="Cümle düzeltme">
        <h2 className="mb-3 text-[20px]">Yazılı / sesli pratik</h2>
        {local ? (
          <Corrector />
        ) : (
          <p className="rounded-xl border border-slate-200 bg-surface p-4 text-[15px]">
            Düzeltme Claude seansında yapılıyor (Claude Desktop → prompt: english_deep_session).
          </p>
        )}
      </section>
      <section aria-label="Kısa diyalog">
        <h2 className="mb-3 text-[20px]">Kısa diyalog</h2>
        <Dialog />
      </section>
    </div>
  )
}
