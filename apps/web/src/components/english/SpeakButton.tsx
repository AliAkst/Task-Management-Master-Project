import { useEffect, useState } from 'react'
import { Volume2 } from 'lucide-react'
import { isSpeaking, speak, speechSupported, stopSpeaking } from '../../lib/speak'

/** Seslendirme dugmesi: konusurken ikinci tiklama durdurur; destek yoksa gizlenir. */
export default function SpeakButton({ text, label = 'Seslendir' }: { text: string; label?: string }) {
  const [on, setOn] = useState(false)
  useEffect(() => {
    if (!on) return
    const t = window.setInterval(() => {
      if (!isSpeaking()) setOn(false)
    }, 300)
    return () => window.clearInterval(t)
  }, [on])
  if (!speechSupported()) return null
  return (
    <button
      type="button"
      aria-label={label}
      aria-pressed={on}
      title={label}
      onClick={() => {
        if (on || isSpeaking()) {
          stopSpeaking()
          setOn(false)
        } else {
          speak(text)
          setOn(true)
        }
      }}
      className={`rounded p-1.5 ${on ? 'bg-slate-900 text-on-ink' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'}`}
    >
      <Volume2 size={16} aria-hidden />
    </button>
  )
}
