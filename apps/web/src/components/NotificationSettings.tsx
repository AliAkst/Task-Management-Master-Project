import { useEffect, useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Loader2, Send, Trash2 } from 'lucide-react'
import { api } from '../lib/api'
import type { UserSettings, UserSettingsUpdate } from '../lib/types'
import { useNotify, useNotifyActions, type NotifyKind } from '../api/notify'
import { formatDateTime } from '../lib/format'
import { Row, Section, Segmented } from './Page'

const KIND_LABEL: Record<NotifyKind, { title: string; hint: string }> = {
  night_plan: { title: 'Gece plan hatırlatması', hint: 'Ertesi gün planlanmadıysa planlama saatinde.' },
  morning: { title: 'Sabah özeti', hint: 'Günün saatli maddeleri ve takvim etkinlikleri.' },
  overdue: { title: 'Geciken kartlar', hint: 'Öğleden sonra; aynı kart 3 gün susturulur.' },
  weekly: { title: 'Haftalık değerlendirme', hint: 'Pazar akşamı; yeterli gün değerlendirmesi varsa.' },
}
const input = 'rounded-md border border-slate-300 bg-surface px-2 py-1.5 text-sm'
const btn =
  'inline-flex items-center gap-1.5 rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:border-slate-900 disabled:opacity-50'
const toInput = (t: string | null | undefined) => (t ? t.slice(0, 5) : '')

type TimeKey = 'planning_time' | 'morning_time' | 'review_time'

/** Saat alanlari /settings'te durur; alandan cikinca kaydedilir. */
function TimeFields() {
  const qc = useQueryClient()
  const settings = useQuery({ queryKey: ['settings'], queryFn: () => api<UserSettings>('/settings/') })
  const save = useMutation({
    mutationFn: (data: UserSettingsUpdate) => api<UserSettings>('/settings/', { method: 'PUT', body: JSON.stringify(data) }),
    onSuccess: (data) => qc.setQueryData(['settings'], data),
  })
  const [vals, setVals] = useState<Record<TimeKey, string>>({ planning_time: '', morning_time: '', review_time: '' })
  useEffect(() => {
    if (!settings.data) return
    setVals({
      planning_time: toInput(settings.data.planning_time),
      morning_time: toInput(settings.data.morning_time),
      review_time: toInput(settings.data.review_time),
    })
  }, [settings.data])
  const commit = (key: TimeKey) => {
    if (vals[key] === toInput(settings.data?.[key])) return
    save.mutate({ [key]: vals[key] ? `${vals[key]}:00` : null })
  }
  const field = (key: TimeKey, label: string, hint: string) => (
    <Row title={label} hint={hint}>
      <input
        type="time"
        aria-label={label}
        className={input}
        value={vals[key]}
        onChange={(e) => setVals({ ...vals, [key]: e.target.value })}
        onBlur={() => commit(key)}
      />
    </Row>
  )
  return (
    <>
      {save.error && <p className="py-2 text-[14px] text-red-700">{save.error.message}</p>}
      {field('planning_time', 'Planlama saati', 'Gece hatırlatması bu saatte (varsayılan 22:30).')}
      {field('morning_time', 'Sabah özeti saati', 'Şablonun ilk bloğu daha erkense 15 dk öncesine çekilir (varsayılan 07:30).')}
      {field('review_time', 'Değerlendirme saati', 'Haftalık değerlendirme Pazar günü bu saatte (varsayılan 20:00).')}
    </>
  )
}

/** Ayarlar -> Bildirimler (Faz 13f). Bot token yalniz yazilirken gorunur; sunucudan asla donmez. */
export default function NotificationSettings() {
  const state = useNotify()
  const act = useNotifyActions()
  const [token, setToken] = useState('')

  const data = state.data
  const telegram = data?.channels.find((c) => c.kind === 'telegram')
  const toast = data?.channels.find((c) => c.kind === 'toast')
  const busy = act.enable.isPending || act.disable.isPending

  const submitToken = (e: FormEvent) => {
    e.preventDefault()
    if (!token.trim() || act.saveTelegram.isPending) return
    // Basarida alan temizlenir; hatada token korunur (tekrar yazmak zorunda kalma)
    act.saveTelegram.mutate(token.trim(), { onSuccess: () => setToken('') })
  }

  const testResult = act.test.data?.results
  const errors = [
    act.enable.error,
    act.disable.error,
    act.test.error,
    act.setToast.error,
    act.removeTelegram.error,
    act.saveSettings.error,
  ]
    .filter(Boolean)
    .map((e) => (e as Error).message)

  return (
    <section id="bildirimler" className="scroll-mt-6">
      <Section
        title="Bildirimler"
        description="Tarayıcı kapalıyken de plan hatırlatması, sabah özeti, geciken kartlar ve haftalık değerlendirme telefonuna (Telegram) ve masaüstüne (Windows bildirimi) gelir. Bilgisayar kapalı ya da uykudayken bildirim gitmez. Gizli panoların içeriği bildirimlere hiç girmez."
      >
        {state.error && <p className="text-[14px] text-red-700">{state.error.message} (asistan servisi çalışıyor mu?)</p>}
        {errors.map((m) => (
          <p key={m} className="text-[14px] text-red-700">
            {m}
          </p>
        ))}
        {data && (
          <div className="divide-y divide-slate-200 border-y border-slate-200">
            <Row
              title="Sunucu bildirimleri"
              hint="Açınca zamanlayıcıya yalnız okuma yetkili bir erişim anahtarı verilir; kapatınca iptal edilir."
            >
              <Segmented
                label="Sunucu bildirimleri"
                value={data.enabled ? 'on' : 'off'}
                onChange={(v) => (v === 'on' ? act.enable.mutate() : act.disable.mutate())}
                options={[
                  { value: 'on', label: 'Açık' },
                  { value: 'off', label: 'Kapalı' },
                ]}
              />
              {busy && <Loader2 size={15} className="animate-spin motion-reduce:animate-none" aria-label="Kaydediliyor" />}
            </Row>

            {data.enabled && (
              <>
                {(Object.keys(KIND_LABEL) as NotifyKind[]).map((k) => (
                  <Row key={k} title={<span className="font-normal">{KIND_LABEL[k].title}</span>} hint={KIND_LABEL[k].hint}>
                    <input
                      type="checkbox"
                      aria-label={KIND_LABEL[k].title}
                      checked={data.settings.kinds[k]}
                      onChange={(e) => act.saveSettings.mutate({ kinds: { [k]: e.target.checked } })}
                    />
                  </Row>
                ))}
                <Row title="Tarayıcı bildirimlerini kapat" hint="Sunucu bildirimi varken aynı hatırlatma iki kez gelmesin.">
                  <input
                    type="checkbox"
                    aria-label="Tarayıcı bildirimlerini kapat"
                    checked={data.settings.browser_reminders_off}
                    onChange={(e) => act.saveSettings.mutate({ browser_reminders_off: e.target.checked })}
                  />
                </Row>
                <TimeFields />

                <div className="py-3.5">
                  <p className="font-semibold">Telegram</p>
                  {telegram?.paired && telegram.is_enabled ? (
                    <div className="mt-1 space-y-1 text-[14px] text-slate-600">
                      <p className="inline-flex items-center gap-1 text-green-700">
                        <Check size={15} aria-hidden /> @{telegram.bot_username} ile bağlı
                      </p>
                      {telegram.last_sent_at && <p>Son gönderim: {formatDateTime(telegram.last_sent_at)}</p>}
                    </div>
                  ) : (
                    <div className="mt-2 space-y-3 text-[14px] text-slate-600">
                      <form onSubmit={submitToken} className="flex flex-wrap items-center gap-2">
                        <label className="sr-only" htmlFor="tg-token">
                          Bot anahtarı
                        </label>
                        <input
                          id="tg-token"
                          type="password"
                          autoComplete="off"
                          placeholder="BotFather'dan aldığın bot token'ı"
                          value={token}
                          onChange={(e) => setToken(e.target.value)}
                          className={`${input} min-w-0 flex-1`}
                        />
                        <button type="submit" disabled={!token.trim() || act.saveTelegram.isPending} className={btn}>
                          {act.saveTelegram.isPending && (
                            <Loader2 size={14} className="animate-spin motion-reduce:animate-none" aria-hidden />
                          )}
                          Kaydet
                        </button>
                      </form>
                      {act.saveTelegram.error && (
                        <p className="text-red-700" role="alert">
                          {act.saveTelegram.error.message}
                        </p>
                      )}
                      {telegram?.bot_username && (
                        <div className="space-y-2">
                          <p>
                            @{telegram.bot_username} bulundu. Telegram’da bota <b>/start</b> yaz, sonra Eşleştir.
                          </p>
                          <button type="button" disabled={act.pair.isPending} onClick={() => act.pair.mutate()} className={btn}>
                            {act.pair.isPending && (
                              <Loader2 size={14} className="animate-spin motion-reduce:animate-none" aria-hidden />
                            )}
                            Eşleştir
                          </button>
                          {act.pair.error && (
                            <p className="text-red-700" role="alert">
                              {act.pair.error.message}
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                  {telegram?.last_error && <p className="mt-1 text-[14px] text-red-700">Son hata: {telegram.last_error}</p>}
                  {telegram && (
                    <button
                      type="button"
                      disabled={act.removeTelegram.isPending}
                      onClick={() => act.removeTelegram.mutate()}
                      className={`${btn} mt-2`}
                    >
                      <Trash2 size={14} aria-hidden /> Kaldır
                    </button>
                  )}
                </div>

                <Row
                  title="Windows bildirimi"
                  hint={toast?.last_error ? `Son hata: ${toast.last_error}` : 'Masaüstünde bildirim olarak görünür.'}
                >
                  <Segmented
                    label="Windows bildirimi"
                    value={toast?.is_enabled ? 'on' : 'off'}
                    onChange={(v) => act.setToast.mutate(v === 'on')}
                    options={[
                      { value: 'on', label: 'Açık' },
                      { value: 'off', label: 'Kapalı' },
                    ]}
                  />
                </Row>

                <Row
                  title="Deneme bildirimi"
                  hint={
                    testResult
                      ? Object.entries(testResult)
                          .map(([k, v]) => `${k}: ${v === 'ok' ? 'gitti' : 'hata'}`)
                          .join(' · ') || 'Etkin kanal yok'
                      : 'Etkin tüm kanallara gönderir.'
                  }
                >
                  <button type="button" disabled={act.test.isPending} onClick={() => act.test.mutate()} className={btn}>
                    {act.test.isPending ? (
                      <Loader2 size={14} className="animate-spin motion-reduce:animate-none" aria-hidden />
                    ) : (
                      <Send size={14} aria-hidden />
                    )}
                    Deneme gönder
                  </button>
                </Row>
              </>
            )}
          </div>
        )}
      </Section>
    </section>
  )
}
