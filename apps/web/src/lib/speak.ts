/** Seslendirme (speechSynthesis) ve Ingilizce sayfasinin tarayici tercihleri. */

export const VOICE_KEY = 'english-voice'
export const RATE_KEY = 'english-rate'
export const LOCAL_CORRECT_KEY = 'english-local-correct'
export const DEFAULT_RATE = 0.9

export function readPref(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

export function writePref(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* depolama kapali: tercih oturumla sinirli kalir */
  }
}

export const speechSupported = (): boolean => typeof window !== 'undefined' && 'speechSynthesis' in window

export function getRate(): number {
  const raw = readPref(RATE_KEY)
  const n = Number(raw)
  return raw !== null && Number.isFinite(n) && n >= 0.7 && n <= 1.2 ? n : DEFAULT_RATE
}

export function localCorrectEnabled(): boolean {
  return readPref(LOCAL_CORRECT_KEY) !== 'off'
}

/** Cevrimici (localService=false) sesin metni uretici sunucusuna gider; varsayilan hep yerel olsun. */
export function isOnlineVoice(v: SpeechSynthesisVoice): boolean {
  return v.localService === false
}

/** Kayitli secim yokken kullanilacak ses: ilk yerel en- sesi (yoksa undefined = tarayici varsayilani). */
export function defaultLocalVoice(voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice | undefined {
  return voices.find((v) => v.lang.toLowerCase().startsWith('en-') && !isOnlineVoice(v))
}

export function isSpeaking(): boolean {
  return speechSupported() && (window.speechSynthesis.speaking || window.speechSynthesis.pending)
}

export function stopSpeaking(): void {
  if (speechSupported()) window.speechSynthesis.cancel()
}

/** Onceki konusmayi keser, yenisini okur. Destek yoksa sessizce hicbir sey yapmaz. */
export function speak(text: string, opts: { voiceURI?: string | null; rate?: number } = {}): void {
  if (!speechSupported() || !text.trim()) return
  const synth = window.speechSynthesis
  synth.cancel()
  const u = new SpeechSynthesisUtterance(text)
  u.lang = 'en-US'
  u.rate = opts.rate ?? getRate()
  const uri = opts.voiceURI ?? readPref(VOICE_KEY)
  const all = synth.getVoices()
  const v = (uri ? all.find((x) => x.voiceURI === uri) : undefined) ?? defaultLocalVoice(all)
  if (v) {
    u.voice = v
    u.lang = v.lang
  }
  synth.speak(u)
}
