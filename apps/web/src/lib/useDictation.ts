import { useCallback, useEffect, useRef, useState } from 'react'

/* Web Speech API tipleri lib.dom'da yok; yalniz kullandigimiz kisim. */
interface SpeechAlternative {
  transcript: string
}
interface SpeechResult {
  isFinal: boolean
  0: SpeechAlternative
}
interface SpeechEvent {
  resultIndex: number
  results: ArrayLike<SpeechResult>
}
interface SpeechRecognitionLike {
  lang: string
  interimResults: boolean
  continuous: boolean
  onresult: ((e: SpeechEvent) => void) | null
  onerror: ((e: { error: string }) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
  abort: () => void
}
type RecognitionCtor = new () => SpeechRecognitionLike

function getCtor(): RecognitionCtor | null {
  if (typeof window === 'undefined') return null
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

export const DICTATION_ERRORS: Record<string, string> = {
  'not-allowed': 'Mikrofon izni verilmedi. Adres çubuğundaki kilit simgesinden mikrofona izin ver.',
  'service-not-allowed': 'Mikrofon izni verilmedi. Adres çubuğundaki kilit simgesinden mikrofona izin ver.',
  'no-speech': 'Ses algılanmadı.',
  'audio-capture': 'Mikrofon bulunamadı.',
  network: 'Ses tanıma servisine ulaşılamadı (internet gerekir).',
}

/** Sonuc gelmeden bu sure gecerse dikte kendiliginden durur. */
export const DICTATION_IDLE_MS = 8000

export interface Dictation {
  supported: boolean
  listening: boolean
  interim: string
  error: string | null
  start: () => void
  stop: () => void
  toggle: () => void
}

/**
 * Konus -> yazi. Motor bagimsiz arayuz: ileride local Whisper ayni donus tipiyle takilabilir.
 * onFinal: kesinlesen her parca icin bir kez cagrilir (ham metin).
 */
export function useDictation({ onFinal, lang = 'tr-TR' }: { onFinal: (text: string) => void; lang?: string }): Dictation {
  const supported = getCtor() !== null
  const [listening, setListening] = useState(false)
  const [interim, setInterim] = useState('')
  const [error, setError] = useState<string | null>(null)
  const rec = useRef<SpeechRecognitionLike | null>(null)
  const timer = useRef<number | null>(null)
  const onFinalRef = useRef(onFinal)
  onFinalRef.current = onFinal

  const clearTimer = () => {
    if (timer.current !== null) window.clearTimeout(timer.current)
    timer.current = null
  }

  const stop = useCallback(() => {
    clearTimer()
    rec.current?.stop()
  }, [])

  const armTimer = useCallback(() => {
    clearTimer()
    timer.current = window.setTimeout(() => rec.current?.stop(), DICTATION_IDLE_MS)
  }, [])

  const start = useCallback(() => {
    const Ctor = getCtor()
    if (!Ctor || rec.current) return
    const r = new Ctor()
    r.lang = lang
    r.interimResults = true
    r.continuous = true
    r.onresult = (e) => {
      armTimer()
      let live = ''
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i]
        if (res.isFinal) {
          const t = res[0].transcript.trim()
          if (t) onFinalRef.current(t)
        } else live += res[0].transcript
      }
      setInterim(live.trim())
    }
    r.onerror = (e) => setError(DICTATION_ERRORS[e.error] ?? (e.error === 'aborted' ? null : `Ses tanıma hatası: ${e.error}`))
    r.onend = () => {
      clearTimer()
      rec.current = null
      setListening(false)
      setInterim('')
    }
    rec.current = r
    setError(null)
    setInterim('')
    try {
      r.start()
      setListening(true)
      armTimer()
    } catch {
      rec.current = null
      setError('Ses tanıma başlatılamadı.')
    }
  }, [lang, armTimer])

  const toggle = useCallback(() => (rec.current ? stop() : start()), [start, stop])

  // Bilesen kaldirilinca dinlemeyi birak
  useEffect(
    () => () => {
      clearTimer()
      const r = rec.current
      if (r) {
        r.onend = null
        r.onresult = null
        r.onerror = null
        r.abort()
        rec.current = null
      }
    },
    [],
  )

  return { supported, listening, interim, error, start, stop, toggle }
}
