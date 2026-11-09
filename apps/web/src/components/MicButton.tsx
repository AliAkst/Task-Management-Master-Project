import { useState, type KeyboardEvent, type ReactNode } from 'react'
import { Mic } from 'lucide-react'
import { useDictation, type Dictation } from '../lib/useDictation'
import { isDictationKey } from '../lib/dictation'
import { usePrefs } from '../stores/prefs'

export interface MicControl {
  /** Dugme (desteklenmiyorsa ya da ayar kapaliysa null). */
  button: ReactNode
  dictation: Dictation
  /** Acik mi: hem tarayici destegi hem ayar. */
  active: boolean
  /** Giris alaninin onKeyDown'unda cagir: Ctrl+M'yi isler. */
  onKey: (e: KeyboardEvent) => void
}

/**
 * Dikte dugmesi + ilk kullanim bilgisi + Ctrl+M. Parent onFinal ile metni girisine ekler.
 * Dugme ve kisayol tek yerden yonetilir; bilgi uyarisi atlanamaz.
 */
export function useMic(onFinal: (text: string) => void): MicControl {
  const enabled = usePrefs((s) => s.dictationEnabled)
  const noticeSeen = usePrefs((s) => s.dictationNoticeSeen)
  const markSeen = usePrefs((s) => s.markDictationNoticeSeen)
  const dictation = useDictation({ onFinal })
  const [notice, setNotice] = useState(false)
  const active = enabled && dictation.supported

  const request = () => {
    if (dictation.listening) dictation.stop()
    else if (!noticeSeen) setNotice(true)
    else dictation.start()
  }

  const button = active ? (
    <span className="relative inline-flex">
      <button
        type="button"
        onClick={request}
        aria-pressed={dictation.listening}
        aria-label="Sesle yaz"
        title="Sesle yaz (Ctrl+M)"
        className={`rounded p-1.5 ${
          dictation.listening
            ? 'bg-rec text-on-ink motion-safe:animate-pulse'
            : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
        }`}
      >
        <Mic size={16} aria-hidden />
      </button>
      {notice && (
        <div
          role="dialog"
          aria-label="Sesli dikte bilgisi"
          className="absolute bottom-full left-0 z-30 mb-1 w-64 rounded-md border border-slate-200 bg-surface p-3 text-left text-[13px] font-normal text-slate-800 shadow-lg"
        >
          <p>
            Sesin tarayıcı üreticisinin (Chrome’da Google, Edge’de Microsoft) sunucusunda metne çevrilir — local model
            kullansan bile.
          </p>
          <div className="mt-2 flex justify-end gap-2">
            <button type="button" className="rounded px-2 py-1 text-slate-600 hover:bg-slate-100" onClick={() => setNotice(false)}>
              Vazgeç
            </button>
            <button
              type="button"
              className="rounded bg-slate-900 px-2 py-1 text-on-ink"
              onClick={() => {
                markSeen()
                setNotice(false)
                dictation.start()
              }}
            >
              Anladım, başlat
            </button>
          </div>
        </div>
      )}
    </span>
  ) : null

  const onKey = (e: KeyboardEvent) => {
    if (active && isDictationKey(e)) {
      e.preventDefault()
      request()
    }
  }

  return { button, dictation, active, onKey }
}

/** Dinleme sirasinda gecici metin + hata satiri. */
export function DictationStatus({ mic, className = '' }: { mic: MicControl; className?: string }) {
  const { interim, error, listening } = mic.dictation
  if (!mic.active || (!listening && !error)) return null
  const isError = !!error && !listening
  return (
    <p className={`text-[12px] ${isError ? 'text-red-700' : 'text-slate-500 italic'} ${className}`} aria-live="polite">
      {isError ? error : interim || 'Dinleniyor…'}
    </p>
  )
}
