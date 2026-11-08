import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type ClipboardEvent,
  type DragEvent,
  type KeyboardEvent,
  type ReactNode,
} from 'react'
import { Bold, Braces, Code, Link2, List, ListChecks, Loader2, Paperclip } from 'lucide-react'
import type { Attachment } from '../lib/types'

const LANGS: [string, string][] = [
  ['', 'Düz metin'],
  ['javascript', 'JavaScript'],
  ['typescript', 'TypeScript'],
  ['python', 'Python'],
  ['bash', 'Bash'],
  ['powershell', 'PowerShell'],
  ['json', 'JSON'],
  ['sql', 'SQL'],
  ['html', 'HTML'],
  ['css', 'CSS'],
  ['csharp', 'C#'],
  ['java', 'Java'],
  ['yaml', 'YAML'],
]

export interface MarkdownEditorHandle {
  insert: (text: string) => void
  focus: () => void
}

interface Props {
  value: string
  onChange: (v: string) => void
  onSubmit: () => void
  onCancel?: () => void
  placeholder?: string
  autoFocus?: boolean
  minRows?: number
  submitLabel?: string
  cancelLabel?: string
  toolbarExtra?: ReactNode
  /** Dosya yapistirma/birakma/📎: yukler, ekleri dondurur; editor imlece baglanti ekler. */
  onFiles?: (files: File[]) => Promise<Attachment[]>
}

const tool = 'rounded p-1.5 text-slate-600 hover:bg-slate-100 hover:text-slate-900'
const FENCE = '```'

const MarkdownEditor = forwardRef<MarkdownEditorHandle, Props>(function MarkdownEditor(
  { value, onChange, onSubmit, onCancel, placeholder, autoFocus, minRows = 3, submitLabel = 'Kaydet', cancelLabel = 'Vazgeç', toolbarExtra, onFiles },
  ref,
) {
  const ta = useRef<HTMLTextAreaElement>(null)
  const [langMenu, setLangMenu] = useState(false)
  const pendingSel = useRef<[number, number] | null>(null)
  const valueRef = useRef(value)
  valueRef.current = value
  const fileInput = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(0)

  /** Asenkron islerden sonra da guncel metne/imlece gore ekler (kapanis degerleri eskiyebilir). */
  const insertLatest = useCallback(
    (text: string) => {
      const el = ta.current
      const v = valueRef.current
      const s = el?.selectionStart ?? v.length
      const e = el?.selectionEnd ?? v.length
      pendingSel.current = [s + text.length, s + text.length]
      onChange(v.slice(0, s) + text + v.slice(e))
      requestAnimationFrame(() => ta.current?.focus())
    },
    [onChange],
  )

  const handleFiles = async (files: File[]) => {
    if (!onFiles || files.length === 0) return
    setUploading((n) => n + files.length)
    try {
      const done = await onFiles(files)
      if (done.length) {
        const md = done
          .map((a) => (a.is_image ? `![${a.filename}](attachment:${a.id})` : `[📎 ${a.filename}](attachment:${a.id})`))
          .join('\n')
        insertLatest(md + '\n')
      }
    } finally {
      setUploading((n) => n - files.length)
    }
  }
  const onPaste = (ev: ClipboardEvent<HTMLTextAreaElement>) => {
    // Excel/Word kopyasi hem metin hem resim tasir: metin varsa normal yapistir
    if (!onFiles || ev.clipboardData.files.length === 0 || ev.clipboardData.getData('text/plain')) return
    ev.preventDefault()
    void handleFiles(Array.from(ev.clipboardData.files))
  }
  const hasFiles = (ev: DragEvent) => Array.from(ev.dataTransfer.types).includes('Files')
  const onDragOver = (ev: DragEvent<HTMLTextAreaElement>) => {
    if (onFiles && hasFiles(ev)) ev.preventDefault()
  }
  const onDrop = (ev: DragEvent<HTMLTextAreaElement>) => {
    if (!onFiles || !hasFiles(ev)) return
    ev.preventDefault()
    ev.stopPropagation() // kart penceresinin genel birakma alani da yuklemesin
    void handleFiles(Array.from(ev.dataTransfer.files))
  }

  // Otomatik yukselme + bekleyen imlec konumu
  useEffect(() => {
    const el = ta.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight + 2}px`
    if (pendingSel.current) {
      el.setSelectionRange(...pendingSel.current)
      pendingSel.current = null
    }
  }, [value])

  useEffect(() => {
    if (autoFocus && ta.current) {
      ta.current.focus()
      const n = ta.current.value.length
      ta.current.setSelectionRange(n, n)
    }
  }, [autoFocus])

  const range = (): [number, number] => [
    ta.current?.selectionStart ?? value.length,
    ta.current?.selectionEnd ?? value.length,
  ]

  /** [start, end) araligini degistirir; sel: eklenen metne gore [bas, son] imlec. */
  const replace = useCallback(
    (start: number, end: number, text: string, sel: [number, number]) => {
      pendingSel.current = [start + sel[0], start + sel[1]]
      onChange(value.slice(0, start) + text + value.slice(end))
      requestAnimationFrame(() => ta.current?.focus())
    },
    [value, onChange],
  )

  useImperativeHandle(ref, () => ({
    insert: (text: string) => {
      const [s, e] = range()
      replace(s, e, text, [text.length, text.length])
    },
    focus: () => ta.current?.focus(),
  }))

  const wrap = (before: string, after: string, fallback: string) => {
    const [s, e] = range()
    const chosen = value.slice(s, e) || fallback
    replace(s, e, before + chosen + after, [before.length, before.length + chosen.length])
  }
  const linePrefix = (prefix: string) => {
    const [s, e] = range()
    const lineStart = value.lastIndexOf('\n', s - 1) + 1
    const block = value.slice(lineStart, e) || 'madde'
    const out = block
      .split('\n')
      .map((l) => prefix + l)
      .join('\n')
    replace(lineStart, e, out, [out.length, out.length])
  }
  const codeBlock = (lang: string) => {
    setLangMenu(false)
    const [s, e] = range()
    const chosen = value.slice(s, e)
    const lead = s > 0 && value[s - 1] !== '\n' ? '\n' : ''
    const head = `${lead}${FENCE}${lang}\n`
    const pos = head.length + chosen.length
    replace(s, e, `${head}${chosen}\n${FENCE}\n`, [pos, pos])
  }
  const link = () => {
    const [s, e] = range()
    const chosen = value.slice(s, e) || 'metin'
    const urlStart = chosen.length + 3
    replace(s, e, `[${chosen}](https://)`, [urlStart, urlStart + 8])
  }

  const insideFence = (pos: number) => (value.slice(0, pos).split(FENCE).length - 1) % 2 === 1

  const onKeyDown = (ev: KeyboardEvent<HTMLTextAreaElement>) => {
    const mod = ev.ctrlKey || ev.metaKey
    if (mod && ev.key === 'Enter') {
      ev.preventDefault()
      onSubmit()
    } else if (ev.key === 'Escape' && onCancel) {
      ev.preventDefault()
      ev.stopPropagation()
      onCancel()
    } else if (mod && ev.key.toLowerCase() === 'b') {
      ev.preventDefault()
      wrap('**', '**', 'kalın')
    } else if (mod && ev.key.toLowerCase() === 'e') {
      ev.preventDefault()
      wrap('`', '`', 'kod')
    } else if (ev.key === 'Tab') {
      const [s, e] = range()
      if (!insideFence(s)) return
      ev.preventDefault()
      if (!ev.shiftKey) {
        replace(s, e, '  ', [2, 2])
      } else {
        const lineStart = value.lastIndexOf('\n', s - 1) + 1
        const m = /^ {1,2}/.exec(value.slice(lineStart))
        if (m) {
          const n = m[0].length
          pendingSel.current = [Math.max(lineStart, s - n), Math.max(lineStart, e - n)]
          onChange(value.slice(0, lineStart) + value.slice(lineStart + n))
        }
      }
    }
  }

  return (
    <div className="space-y-2">
      <div className="rounded-md border border-slate-300 bg-surface focus-within:border-slate-500">
        <div className="relative flex flex-wrap items-center gap-0.5 border-b border-slate-200 px-1.5 py-1">
          <button type="button" className={tool} title="Kalın (Ctrl+B)" aria-label="Kalın" onClick={() => wrap('**', '**', 'kalın')}>
            <Bold size={16} aria-hidden />
          </button>
          <button type="button" className={tool} title="Satır içi kod (Ctrl+E)" aria-label="Satır içi kod" onClick={() => wrap('`', '`', 'kod')}>
            <Code size={16} aria-hidden />
          </button>
          <button
            type="button"
            className={tool}
            title="Kod bloğu"
            aria-label="Kod bloğu"
            aria-haspopup="menu"
            aria-expanded={langMenu}
            onClick={() => setLangMenu((o) => !o)}
          >
            <Braces size={16} aria-hidden />
          </button>
          <button type="button" className={tool} title="Liste" aria-label="Liste" onClick={() => linePrefix('- ')}>
            <List size={16} aria-hidden />
          </button>
          <button type="button" className={tool} title="Görev listesi" aria-label="Görev listesi" onClick={() => linePrefix('- [ ] ')}>
            <ListChecks size={16} aria-hidden />
          </button>
          <button type="button" className={tool} title="Bağlantı" aria-label="Bağlantı" onClick={link}>
            <Link2 size={16} aria-hidden />
          </button>
          {onFiles && (
            <>
              <button type="button" className={tool} title="Dosya ekle" aria-label="Dosya ekle" onClick={() => fileInput.current?.click()}>
                {uploading > 0 ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <Paperclip size={16} aria-hidden />}
              </button>
              <input
                ref={fileInput}
                type="file"
                multiple
                className="hidden"
                aria-hidden
                tabIndex={-1}
                onChange={(e) => {
                  void handleFiles(Array.from(e.target.files ?? []))
                  e.target.value = ''
                }}
              />
            </>
          )}
          {toolbarExtra}
          {langMenu && (
            <ul
              role="menu"
              className="absolute top-full left-8 z-20 mt-1 max-h-60 w-40 overflow-y-auto rounded-md border border-slate-200 bg-surface py-1 text-[14px] shadow-lg"
            >
              {LANGS.map(([id, label]) => (
                <li key={id || 'plain'} role="none">
                  <button type="button" role="menuitem" className="block w-full px-3 py-1 text-left hover:bg-slate-100" onClick={() => codeBlock(id)}>
                    {label}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <textarea
          ref={ta}
          rows={minRows}
          className="block w-full resize-none rounded-b-md bg-surface px-3 py-2 text-[15px] focus:outline-none"
          placeholder={placeholder}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          onPaste={onPaste}
          onDragOver={onDragOver}
          onDrop={onDrop}
          aria-label={placeholder ?? 'Markdown metni'}
        />
      </div>
      <div className="flex items-center gap-3">
        <button type="button" onClick={onSubmit} className="rounded-md bg-slate-900 px-3 py-1 text-sm text-on-ink">
          {submitLabel}
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel} className="text-sm text-slate-600 hover:underline">
            {cancelLabel}
          </button>
        )}
        <span className="ml-auto text-[12px] text-slate-500">Ctrl+Enter kaydeder, Esc vazgeçer</span>
      </div>
    </div>
  )
})

export default MarkdownEditor
