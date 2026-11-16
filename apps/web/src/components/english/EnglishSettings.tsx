import { useEffect, useState } from 'react'
import type { EnglishProfile } from '../../api/english'
import {
  DEFAULT_RATE,
  LOCAL_CORRECT_KEY,
  RATE_KEY,
  VOICE_KEY,
  getRate,
  localCorrectEnabled,
  readPref,
  speak,
  speechSupported,
  writePref,
} from '../../lib/speak'
import { Row } from '../Page'
import SetupForm from './SetupForm'

function useEnglishVoices(): SpeechSynthesisVoice[] {
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([])
  useEffect(() => {
    if (!speechSupported()) return
    const synth = window.speechSynthesis
    const load = () => setVoices(synth.getVoices().filter((v) => v.lang.toLowerCase().startsWith('en-')))
    load()
    synth.addEventListener('voiceschanged', load) // ilk acilista liste bos gelebilir
    return () => synth.removeEventListener('voiceschanged', load)
  }, [])
  return voices
}

export default function EnglishSettings({ profile }: { profile: EnglishProfile }) {
  const voices = useEnglishVoices()
  const [voice, setVoice] = useState(readPref(VOICE_KEY) ?? '')
  const [rate, setRate] = useState(getRate())
  const [localCorrect, setLocalCorrect] = useState(localCorrectEnabled())

  return (
    <div className="space-y-8">
      <section aria-label="Profil">
        <h2 className="mb-3 text-[20px]">Profil</h2>
        <SetupForm initial={profile} submitLabel="Kaydet" />
      </section>

      <section aria-label="Ses ve düzeltme" className="divide-y divide-slate-200">
        <Row title="Yerel düzeltme" hint="Kapalıysa Pratik sekmesi düzeltme yerine Claude seansına yönlendirir.">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={localCorrect}
              onChange={(e) => {
                setLocalCorrect(e.target.checked)
                writePref(LOCAL_CORRECT_KEY, e.target.checked ? 'on' : 'off')
              }}
            />
            Açık
          </label>
        </Row>
        {speechSupported() ? (
          <>
            <Row title="Ses" hint="Tarayıcının İngilizce sesleri.">
              <select
                aria-label="Ses seçimi"
                className="max-w-56 rounded-md border border-slate-300 bg-surface px-2 py-1 text-sm"
                value={voice}
                onChange={(e) => {
                  setVoice(e.target.value)
                  writePref(VOICE_KEY, e.target.value)
                }}
              >
                <option value="">Varsayılan</option>
                {voices.map((v) => (
                  <option key={v.voiceURI} value={v.voiceURI}>
                    {v.name} ({v.lang})
                  </option>
                ))}
              </select>
            </Row>
            <Row title="Hız" hint={`0.7–1.2, varsayılan ${DEFAULT_RATE}`}>
              <input
                type="range"
                aria-label="Konuşma hızı"
                min={0.7}
                max={1.2}
                step={0.05}
                value={rate}
                onChange={(e) => {
                  const n = Number(e.target.value)
                  setRate(n)
                  writePref(RATE_KEY, String(n))
                }}
              />
              <span className="w-10 text-sm tabular-nums">{rate.toFixed(2)}</span>
              <button
                type="button"
                onClick={() => speak('Hello, this is a test sentence.', { voiceURI: voice || null, rate })}
                className="rounded-md border border-slate-300 px-2 py-1 text-sm hover:bg-slate-100"
              >
                Dene
              </button>
            </Row>
          </>
        ) : (
          <Row title="Seslendirme" hint="Bu tarayıcı seslendirmeyi desteklemiyor.">
            <span />
          </Row>
        )}
      </section>

      <p className="max-w-prose text-sm text-slate-600">
        Dikte, tarayıcının konuşma tanıma servisine (Chrome/Edge: üreticinin sunucusu) ses gönderir.
      </p>
    </div>
  )
}
