import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check } from 'lucide-react'
import { api } from '../lib/api'
import type { UserSettings, UserSettingsUpdate } from '../lib/types'
import { usePermissions, useSetPermission, type Permission } from '../api/assistant'
import IntegrationsSettings from '../components/IntegrationsSettings'
import ModelSettings from '../components/ModelSettings'
import { PageHeader, Row, Segmented } from '../components/Page'
import { usePrefs } from '../stores/prefs'

const MODE_LABEL: Record<Permission['mode'], string> = {
  ask: 'Bana sor',
  auto: 'Otomatik',
  never: 'Asla',
}

const SECTIONS = [
  { id: 'ritim', label: 'Günün ritmi' },
  { id: 'model', label: 'Asistan modeli' },
  { id: 'izinler', label: 'Asistan izinleri' },
  { id: 'ses', label: 'Ses' },
  { id: 'baglantilar', label: 'Bağlantılar' },
]

/** AI'in hangi islemleri sormadan yapabilecegi: kullanici karar verir. */
function AssistantPermissions() {
  const perms = usePermissions()
  const set = useSetPermission()
  return (
    <section id="izinler" className="scroll-mt-6">
      <h2 className="text-[22px]">Asistan izinleri</h2>
      <p className="mt-1 mb-2 max-w-prose text-[15px] text-slate-600">
        Asistan bir şey yapmak istediğinde ne olsun? “Bana sor” seçiliyse sohbette onay kartı çıkar; “Asla” seçtiğin
        işlemi asistan önermez bile.
      </p>
      {perms.error && <p className="text-[14px] text-red-700">{perms.error.message} (asistan servisi çalışıyor mu?)</p>}
      <div className="divide-y divide-slate-200 border-y border-slate-200">
        {perms.data?.map((p) => (
          <Row key={p.action_type} title={<span className="font-normal">{p.label}</span>}>
            <Segmented
              label={p.label}
              value={p.mode}
              onChange={(mode) => set.mutate({ actionType: p.action_type, mode })}
              options={(Object.keys(MODE_LABEL) as Permission['mode'][]).map((m) => ({ value: m, label: MODE_LABEL[m] }))}
            />
          </Row>
        ))}
      </div>
    </section>
  )
}

/** Sesli dikte tercihleri: cihaza ozel (localStorage), sunucuya yazilmaz. */
function VoiceSettings() {
  const enabled = usePrefs((s) => s.dictationEnabled)
  const autoSend = usePrefs((s) => s.dictationAutoSend)
  const setEnabled = usePrefs((s) => s.setDictationEnabled)
  const setAutoSend = usePrefs((s) => s.setDictationAutoSend)
  const onOff = [{ value: 'on', label: 'Açık' }, { value: 'off', label: 'Kapalı' }]
  return (
    <section id="ses" className="scroll-mt-6">
      <h2 className="text-[22px]">Ses</h2>
      <p className="mt-1 mb-2 max-w-prose text-[15px] text-slate-600">
        Bu tercihler yalnız bu cihazda geçerlidir. Dikte tarayıcının konuşma tanımasını kullanır (Chrome, Edge).
      </p>
      <div className="divide-y divide-slate-200 border-y border-slate-200">
        <Row title="Sesli dikte" hint="Asistan, not ve yapılacaklar girişlerinde mikrofon düğmesi (Ctrl+M).">
          <Segmented label="Sesli dikte" value={enabled ? 'on' : 'off'} onChange={(v) => setEnabled(v === 'on')} options={onOff} />
        </Row>
        <Row title="Dikte bitince mesajı gönder" hint="Yalnız asistan panelinde; kapalıyken metin yalnız girişe yazılır.">
          <Segmented label="Dikte bitince mesajı gönder" value={autoSend ? 'on' : 'off'} onChange={(v) => setAutoSend(v === 'on')} options={onOff} />
        </Row>
      </div>
    </section>
  )
}

const toInput =(t: string | null | undefined) => (t ? t.slice(0, 5) : '')

/** Tarayici bildirim izni (hatirlaticilar uygulama aciktayken bildirim olarak da gelir). */
function NotificationPermission() {
  const supported = typeof window !== 'undefined' && 'Notification' in window
  const [perm, setPerm] = useState(supported ? Notification.permission : 'denied')
  return (
    <Row title="Tarayıcı bildirimleri" hint="Uygulama açıkken hatırlatmalar bildirim olarak da gelir.">
      {!supported ? (
        <span className="text-[14px] text-slate-500">Bu tarayıcı desteklemiyor</span>
      ) : perm === 'granted' ? (
        <span className="inline-flex items-center gap-1 text-[14px] text-green-700"><Check size={15} aria-hidden /> Açık</span>
      ) : perm === 'denied' ? (
        <span className="max-w-56 text-right text-[14px] text-slate-500">Engellendi; tarayıcının site ayarlarından izin ver</span>
      ) : (
        <button type="button" onClick={() => Notification.requestPermission().then(setPerm)} className="rounded-md border border-slate-300 px-3 py-1 text-sm hover:border-slate-900">
          İzin ver
        </button>
      )}
    </Row>
  )
}

function DayRhythm() {
  const qc = useQueryClient()
  const settings = useQuery({ queryKey: ['settings'], queryFn: () => api<UserSettings>('/settings/') })
  const save = useMutation({
    mutationFn: (data: UserSettingsUpdate) => api<UserSettings>('/settings/', { method: 'PUT', body: JSON.stringify(data) }),
    onSuccess: (data) => qc.setQueryData(['settings'], data),
  })
  const [planning, setPlanning] = useState('')
  const [review, setReview] = useState('')

  useEffect(() => {
    if (!settings.data) return
    setPlanning(toInput(settings.data.planning_time))
    setReview(toInput(settings.data.review_time))
  }, [settings.data])

  // Saat alani: yazarken degil, alandan cikinca kaydedilir
  const saveTime = (key: 'planning_time' | 'review_time', v: string) => {
    const current = toInput(settings.data?.[key])
    if (v !== current) save.mutate({ [key]: v ? `${v}:00` : null })
  }

  return (
    <section id="ritim" className="scroll-mt-6">
      <div className="flex items-baseline justify-between gap-4">
        <h2 className="text-[22px]">Günün ritmi</h2>
        <span className="text-[13px] text-slate-500" aria-live="polite">
          {save.isPending ? 'Kaydediliyor…' : save.isSuccess ? 'Kaydedildi' : ''}
        </span>
      </div>
      <p className="mt-1 mb-2 max-w-prose text-[15px] text-slate-600">
        Günü ne zaman planlayıp ne zaman değerlendirmek istediğin. Bu saatlerde uygulama seni hatırlatır.
      </p>
      {settings.error && <p className="text-[14px] text-red-700">{settings.error.message}</p>}
      {save.error && <p className="text-[14px] text-red-700">{save.error.message}</p>}
      {settings.data && (
        <div className="divide-y divide-slate-200 border-y border-slate-200">
          <Row title="Planlama saati" hint="“Bugün” sayfası bu saatte planlama ile açılır.">
            <input type="time" className="rounded-md border border-slate-300 bg-white px-2 py-1" value={planning} onChange={(e) => setPlanning(e.target.value)} onBlur={(e) => saveTime('planning_time', e.target.value)} aria-label="Planlama saati" />
          </Row>
          <Row title="Gün sonu değerlendirme saati" hint="Bu saatten sonra “Bugün” sayfası değerlendirmeyle açılır.">
            <input type="time" className="rounded-md border border-slate-300 bg-white px-2 py-1" value={review} onChange={(e) => setReview(e.target.value)} onBlur={(e) => saveTime('review_time', e.target.value)} aria-label="Gün sonu değerlendirme saati" />
          </Row>
          <Row title="Hatırlatmalar" hint={`Saat dilimi: ${settings.data.timezone}`}>
            <Segmented
              label="Hatırlatmalar"
              value={settings.data.reminders_enabled ? 'on' : 'off'}
              onChange={(v) => save.mutate({ reminders_enabled: v === 'on' })}
              options={[{ value: 'on', label: 'Açık' }, { value: 'off', label: 'Kapalı' }]}
            />
          </Row>
          <NotificationPermission />
        </div>
      )}
    </section>
  )
}

export default function SettingsPage() {
  return (
    <div className="mx-auto w-full max-w-6xl p-4 sm:p-6">
      <PageHeader title="Ayarlar" subtitle="Günün ritmi, asistanın hangi modelle çalıştığı ve neleri sormadan yapabileceği." />
      <div className="grid gap-10 lg:grid-cols-[200px_minmax(0,1fr)]">
        <nav aria-label="Ayar bölümleri" className="hidden lg:block">
          <ul className="sticky top-6 space-y-1 border-l border-slate-200 text-[15px]">
            {SECTIONS.map((s) => (
              <li key={s.id}>
                <a href={`#${s.id}`} className="-ml-px block border-l-2 border-transparent py-1 pl-3 text-slate-600 hover:border-slate-900 hover:text-slate-900">
                  {s.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
        <div className="max-w-3xl space-y-12">
          <DayRhythm />
          <div id="model" className="scroll-mt-6"><ModelSettings /></div>
          <AssistantPermissions />
          <VoiceSettings />
          <IntegrationsSettings />
        </div>
      </div>
    </div>
  )
}
