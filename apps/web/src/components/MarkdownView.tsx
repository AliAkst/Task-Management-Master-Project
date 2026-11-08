import { Children, isValidElement, useState, type ReactElement, type ReactNode } from 'react'
import Markdown, { type Components } from 'react-markdown'
import rehypeHighlight from 'rehype-highlight'
import remarkGfm from 'remark-gfm'
import { Check, Copy } from 'lucide-react'

const REMARK = [remarkGfm]
const REHYPE: [typeof rehypeHighlight, { detect: boolean; ignoreMissing: boolean }][] = [
  [rehypeHighlight, { detect: false, ignoreMissing: true }],
]

/** Vurgulanmis (span'li) kod agacindan duz metni cikarir. */
function textOf(node: ReactNode): string {
  if (node == null || typeof node === 'boolean') return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(textOf).join('')
  if (isValidElement<{ children?: ReactNode }>(node)) return textOf(node.props.children)
  return ''
}

function CodeBlock({ children }: { children?: ReactNode }) {
  const [copied, setCopied] = useState(false)
  const code = Children.toArray(children).find(isValidElement) as
    | ReactElement<{ className?: string; children?: ReactNode }>
    | undefined
  const lang = /language-([\w+#-]+)/.exec(code?.props.className ?? '')?.[1]
  const copy = () => {
    const text = textOf(children).replace(/\n$/, '')
    navigator.clipboard
      ?.writeText(text)
      .then(() => {
        setCopied(true)
        setTimeout(() => setCopied(false), 1500)
      })
      .catch(() => {})
  }
  return (
    <div className="my-2 overflow-hidden rounded-md border border-slate-200 bg-[var(--code-bg)]">
      <div className="flex items-center justify-between border-b border-slate-200 px-3 py-1 text-[12px] text-slate-600">
        <span>{lang ?? 'metin'}</span>
        <button
          type="button"
          onClick={copy}
          className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-slate-200"
          aria-label="Kodu kopyala"
        >
          {copied ? <Check size={13} aria-hidden /> : <Copy size={13} aria-hidden />}
          {copied ? 'Kopyalandı' : 'Kopyala'}
        </button>
      </div>
      <pre className="overflow-x-auto px-3 py-2 font-mono text-[13px] leading-relaxed text-[var(--code-fg)]">{children}</pre>
    </div>
  )
}

const components: Components = {
  pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
  code: ({ className, children }) =>
    className ? (
      <code className={className}>{children}</code>
    ) : (
      <code className="rounded bg-[var(--code-bg)] px-1 py-0.5 font-mono text-[0.9em]">{children}</code>
    ),
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
  table: ({ children }) => (
    <div className="my-2 overflow-x-auto">
      <table className="border-collapse text-[14px]">{children}</table>
    </div>
  ),
  th: ({ children }) => <th className="border border-slate-300 px-2 py-1 text-left font-semibold">{children}</th>,
  td: ({ children }) => <td className="border border-slate-300 px-2 py-1">{children}</td>,
}

interface Props {
  content: string
  className?: string
}

/** Markdown gosterimi: GFM, kod vurgulama + kopyala. Ham HTML kapali (react-markdown varsayilani). */
export default function MarkdownView({ content, className = '' }: Props) {
  return (
    <div
      className={`break-words [&_a]:text-blue-700 [&_a]:underline [&_blockquote]:border-l-2 [&_blockquote]:border-slate-300 [&_blockquote]:pl-3 [&_blockquote]:text-slate-600 [&_h1]:text-lg [&_h1]:font-semibold [&_h2]:font-semibold [&_h3]:font-semibold [&_li]:ml-4 [&_ol]:list-decimal [&_p+p]:mt-2 [&_ul]:list-disc [&_li:has(>input)]:ml-0 [&_li:has(>input)]:list-none ${className}`}
    >
      <Markdown remarkPlugins={REMARK} rehypePlugins={REHYPE} components={components}>
        {content}
      </Markdown>
    </div>
  )
}
