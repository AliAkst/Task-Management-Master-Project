import { useRef } from 'react'
import { ExternalLink, Download, FileText, Loader2, Paperclip, Trash2 } from 'lucide-react'
import { useDeleteAttachment } from '../api/attachments'
import { formatBytes, formatDateTime } from '../lib/format'
import type { Attachment } from '../lib/types'

interface Props {
  cardId: number
  boardId: number
  attachments: Attachment[]
  pending: string[]
  error: string | null
  onFiles: (files: File[]) => void
}

/** Kartin "Ekler" bolumu: liste, Ac / Indir / Sil, "Dosya ekle". */
export default function AttachmentsSection({ cardId, boardId, attachments, pending, error, onFiles }: Props) {
  const remove = useDeleteAttachment(cardId, boardId)
  const input = useRef<HTMLInputElement>(null)
  const act = 'inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[13px] text-slate-600 hover:bg-slate-100 hover:text-slate-900'

  return (
    <div className="mt-7">
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <h3 className="text-[15px] font-semibold text-slate-900">
          Ekler {attachments.length > 0 && <span className="font-normal text-slate-500 tabular-nums">{attachments.length}</span>}
        </h3>
        <button type="button" onClick={() => input.current?.click()} className="inline-flex items-center gap-1 text-[13px] text-blue-700 hover:underline">
          <Paperclip size={13} aria-hidden /> Dosya ekle
        </button>
        <input
          ref={input}
          type="file"
          multiple
          className="hidden"
          aria-hidden
          tabIndex={-1}
          onChange={(e) => {
            onFiles(Array.from(e.target.files ?? []))
            e.target.value = ''
          }}
        />
      </div>
      <ul className="divide-y divide-slate-100">
        {attachments.map((a) => (
          <li key={a.id} className="flex items-center gap-3 py-1.5">
            {a.is_image ? (
              <img src={a.url} alt="" loading="lazy" className="h-12 w-12 shrink-0 rounded border border-slate-200 object-cover" />
            ) : (
              <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded border border-slate-200 bg-slate-50 text-slate-500">
                <FileText size={20} aria-hidden />
              </span>
            )}
            <div className="min-w-0 flex-1">
              <p className="truncate text-[14px] text-slate-900" title={a.filename}>{a.filename}</p>
              <p className="text-[12px] text-slate-500">
                {formatBytes(a.size_bytes)} · {formatDateTime(a.created_at)}
              </p>
            </div>
            <a href={a.url} target="_blank" rel="noopener noreferrer" className={act} aria-label={`${a.filename} dosyasını aç`}>
              <ExternalLink size={13} aria-hidden /> Aç
            </a>
            <a href={`${a.url}&download=1`} download={a.filename} className={act} aria-label={`${a.filename} dosyasını indir`}>
              <Download size={13} aria-hidden /> İndir
            </a>
            <button
              type="button"
              disabled={remove.isPending && remove.variables === a.id}
              onClick={() => confirm(`“${a.filename}” silinsin mi?`) && remove.mutate(a.id)}
              className={`${act} hover:text-red-700`}
              aria-label={`${a.filename} dosyasını sil`}
            >
              <Trash2 size={13} aria-hidden /> Sil
            </button>
          </li>
        ))}
        {pending.map((name, i) => (
          <li key={`p-${i}`} className="flex items-center gap-3 py-1.5 text-[14px] text-slate-600" aria-live="polite">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded border border-dashed border-slate-300">
              <Loader2 size={18} className="animate-spin" aria-hidden />
            </span>
            <span className="truncate">{name} yükleniyor…</span>
          </li>
        ))}
      </ul>
      {attachments.length === 0 && pending.length === 0 && (
        <p className="text-[13px] text-slate-500">Dosyayı buraya, nota ya da kart penceresine sürükleyip bırakabilirsin.</p>
      )}
      {error && <p className="mt-1 text-sm text-red-700" role="alert">{error}</p>}
      {remove.error && <p className="mt-1 text-sm text-red-700">{remove.error.message}</p>}
    </div>
  )
}
