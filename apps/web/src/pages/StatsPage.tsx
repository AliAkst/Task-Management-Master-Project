import { useState, type ReactNode } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { localDay, shiftDay, useAnalytics } from '../api/dayPlans'
import { PageHeader, Segmented } from '../components/Page'
import { formatDuration } from '../lib/format'
import { useThemeColors } from '../hooks/useThemeColors'

// Kategorik palet ve zemin/eksen renkleri CSS degiskenlerinden (--chart-1..4, slate) gelir: useThemeColors
const BAR_RADIUS: [number, number, number, number] = [4, 4, 0, 0]

const RANGES = [
  { days: 7, label: '7 gün' },
  { days: 30, label: '30 gün' },
  { days: 90, label: '90 gün' },
]
const WEEKDAYS = ['Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt', 'Paz']
const short = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short' })
const dayLabel = (iso: string) => {
  const [y, m, d] = iso.split('-').map(Number)
  return short.format(new Date(y, m - 1, d))
}

/** Defter satiri: kutu yok; sayi, ne oldugu ve tek cumlelik anlami. */
function Figure({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="px-5 py-1 first:pl-0">
      <div className="font-display text-[34px] leading-tight font-[650] text-slate-900 tabular-nums">{value}</div>
      <div className="text-[15px] font-semibold text-slate-800">{label}</div>
      {hint && <div className="mt-0.5 text-[13px] text-slate-500">{hint}</div>}
    </div>
  )
}

function Panel({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <section className="border-t border-slate-300 pt-3">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h2 className="text-[18px]">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  )
}

/** Veri yokken bos eksen cizmek yerine ne zaman dolacagini soyler. */
function Empty({ children, height }: { children: ReactNode; height: number }) {
  return (
    <div style={{ height }} className="flex items-center justify-center rounded-md border border-dashed border-slate-300 px-6 text-center text-[14px] text-slate-500">
      {children}
    </div>
  )
}

/** Recharts ipucu: metin murekkep tonlarinda, renkli isaret kimligi tasir. */
function ChartTip({
  active,
  payload,
  label,
  unit,
}: {
  active?: boolean
  payload?: { name?: string; value?: number; color?: string; dataKey?: string }[]
  label?: string | number
  unit?: 'min'
}) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-md border border-slate-200 bg-surface px-3 py-2 text-[13px] shadow-[0_2px_8px_rgb(23_32_56/0.08)]">
      <p className="mb-1 font-semibold text-slate-900">{label}</p>
      {payload.map((p) => (
        <p key={String(p.dataKey)} className="flex items-center gap-2 text-slate-700">
          <span className="h-2 w-2 rounded-full" style={{ backgroundColor: p.color }} aria-hidden />
          {p.name}
          <span className="ml-auto pl-3 font-semibold text-slate-900 tabular-nums">
            {unit === 'min' ? formatDuration((p.value ?? 0) * 60) : p.value}
          </span>
        </p>
      ))}
    </div>
  )
}



export default function StatsPage() {
  const tc = useThemeColors()
  const C = { s1: tc.s1, s2: tc.s2, s3: tc.s3, s4: tc.s4 }
  const SURFACE = tc.paper // sayfa zemini: 2px bosluk/halka zemin renginde
  const GRID = tc.grid
  const AXIS = { fontSize: 12, fill: tc.axis }
  const CURSOR = { fill: tc.cursor }
  // Lejant metni metin renginde; kimligi yanindaki renkli isaret tasir
  const legendText = (value: string) => <span style={{ color: tc.legend }}>{value}</span>
  const [days, setDays] = useState(7)
  const [showTable, setShowTable] = useState(false)
  const end = localDay()
  const start = shiftDay(end, -(days - 1))
  const q = useAnalytics(start, end)
  const s = q.data

  const daily = (s?.days ?? []).map((d) => ({ ...d, label: dayLabel(d.date) }))
  const hours = (s?.productive_hours ?? []).map((m, h) => ({ hour: `${String(h).padStart(2, '0')}`, minutes: m }))
  const weekdays = (s?.weekdays ?? []).map((m, i) => ({ day: WEEKDAYS[i], minutes: m }))
  const moods = daily.filter((d) => d.mood != null || d.energy != null)
  const acc = s?.estimate_accuracy
  const anyPlan = daily.some((d) => d.planned + d.unplanned > 0)
  const anyTime = daily.some((d) => d.tracked_min > 0)
  const maxBoard = Math.max(1, ...(s?.boards ?? []).map((b) => Math.max(b.tracked_min, b.budget_min ?? 0)))

  return (
    <div className="mx-auto w-full max-w-6xl p-4 sm:p-6">
      <PageHeader
        title="İstatistik"
        subtitle={`${dayLabel(start)} – ${dayLabel(end)}: plana ne kadar uydun, zamanın nereye gitti`}
        actions={<Segmented label="Aralık" value={days} onChange={setDays} options={RANGES.map((r) => ({ value: r.days, label: r.label }))} />}
      />

      {q.isLoading && <p className="text-slate-500">Yükleniyor…</p>}
      {q.error && <p className="text-red-600">{q.error.message}</p>}

      {s && (
        <>
          <div className="mb-10 grid grid-cols-2 gap-y-4 divide-slate-200 md:grid-cols-4 md:divide-x">
            <Figure label="Çalışılan süre" value={formatDuration(s.totals.tracked_min * 60)} hint={`günde ort. ${formatDuration((s.totals.tracked_min / s.totals.days) * 60)}`} />
            <Figure
              label="Plana uyum"
              value={s.totals.completion_rate == null ? '—' : `%${Math.round(s.totals.completion_rate * 100)}`}
              hint={`${s.totals.done_items}/${s.totals.planned_items} planlı madde yapıldı`}
            />
            <Figure label="Değerlendirme serisi" value={`${s.totals.current_streak} gün`} hint={`${s.totals.reviewed_days}/${s.totals.days} gün değerlendirildi`} />
            <Figure
              label="Tahmin doğruluğu"
              value={acc?.mean_ratio == null ? '—' : `×${acc.mean_ratio.toFixed(2)}`}
              hint={
                acc?.mean_ratio == null
                  ? 'Tahminli + süresi tutulan kart tamamlayınca görünür'
                  : acc.mean_ratio > 1.05
                    ? `İşler tahminden ort. %${Math.round((acc.mean_ratio - 1) * 100)} uzun sürüyor (${acc.sample_size} kart)`
                    : acc.mean_ratio < 0.95
                      ? `İşler tahminden ort. %${Math.round((1 - acc.mean_ratio) * 100)} kısa sürüyor (${acc.sample_size} kart)`
                      : `Tahminlerin isabetli (${acc.sample_size} kart)`
              }
            />
          </div>

          <div className="space-y-10">
          <div className="grid gap-x-10 gap-y-10 lg:grid-cols-2">
            <Panel
              title="Günlük plan sonuçları (madde sayısı)"
              action={<button onClick={() => setShowTable((t) => !t)} className="text-xs text-blue-600 hover:underline">{showTable ? 'Grafik' : 'Tablo olarak göster'}</button>}
            >
              {showTable ? (
                <div className="max-h-64 overflow-auto">
                  <table className="w-full text-xs">
                    <thead className="text-left text-slate-500">
                      <tr><th className="py-1">Gün</th><th>Plan</th><th>Yapıldı</th><th>Kısmen</th><th>Yapılmadı</th><th>Ertelendi</th><th>Plansız</th><th>Süre</th></tr>
                    </thead>
                    <tbody className="tabular-nums">
                      {daily.map((d) => (
                        <tr key={d.date} className="border-t border-slate-100">
                          <td className="py-1">{d.label}</td><td>{d.planned}</td><td>{d.done}</td><td>{d.partial}</td><td>{d.not_done}</td><td>{d.postponed}</td><td>{d.unplanned}</td><td>{formatDuration(d.tracked_min * 60)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : !anyPlan ? (
                <Empty height={240}>Bu aralıkta gün planı yok. “Bugün” sayfasından günü planladıkça sonuçlar burada birikir.</Empty>
              ) : (
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={daily} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                    <CartesianGrid vertical={false} stroke={GRID} strokeDasharray="3 4" />
                    <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                    <YAxis allowDecimals={false} tick={AXIS} tickLine={false} axisLine={false} />
                    <Tooltip content={<ChartTip />} cursor={CURSOR} />
                    <Legend wrapperStyle={{ fontSize: 12 }} iconType="circle" formatter={legendText} />
                    <Bar dataKey="done" name="Yapıldı" stackId="o" fill={C.s1} stroke={SURFACE} strokeWidth={2} />
                    <Bar dataKey="partial" name="Kısmen" stackId="o" fill={C.s2} stroke={SURFACE} strokeWidth={2} />
                    <Bar dataKey="not_done" name="Yapılmadı" stackId="o" fill={C.s3} stroke={SURFACE} strokeWidth={2} />
                    <Bar dataKey="postponed" name="Ertelendi" stackId="o" fill={C.s4} stroke={SURFACE} strokeWidth={2} radius={BAR_RADIUS} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </Panel>

            <Panel title="Günlük çalışma süresi (dakika)">
              {!anyTime ? (
                <Empty height={240}>Bu aralıkta kronometre kaydı yok. Bir kartta “Başla”ya bastığında süre burada görünür.</Empty>
              ) : (
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={daily} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <CartesianGrid vertical={false} stroke={GRID} strokeDasharray="3 4" />
                  <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                  <YAxis tick={AXIS} tickLine={false} axisLine={false} />
                  <Tooltip content={<ChartTip unit="min" />} cursor={CURSOR} />
                  <Bar dataKey="tracked_min" name="Süre" fill={C.s1} radius={BAR_RADIUS} />
                </BarChart>
              </ResponsiveContainer>
              )}
            </Panel>
          </div>

          <div className="grid gap-x-10 gap-y-10 lg:grid-cols-2">
            <Panel title="Board'lara göre süre ve haftalık hedef">
              {s.boards.filter((b) => b.tracked_min > 0 || b.budget_min).length === 0 && (
                <Empty height={120}>Bu aralıkta hiçbir board'a süre kaydedilmedi.</Empty>
              )}
              <ul className="space-y-2.5">
                {s.boards
                  .filter((b) => b.tracked_min > 0 || b.budget_min)
                  .map((b) => {
                    const over = b.budget_min != null && b.tracked_min >= b.budget_min
                    return (
                      <li key={b.board_id ?? 'none'} className="text-sm" title={`${b.name}: ${formatDuration(b.tracked_min * 60)}${b.budget_min ? ` / hedef ${formatDuration(b.budget_min * 60)}` : ''} · ${b.completed_cards} kart tamamlandı`}>
                        <div className="mb-1 flex items-baseline justify-between gap-2">
                          <span className="flex items-center gap-1.5 text-slate-800">
                            <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: b.color }} />
                            {b.name}
                          </span>
                          <span className="text-xs text-slate-500 tabular-nums">
                            {formatDuration(b.tracked_min * 60)}
                            {b.budget_min != null && ` / ${formatDuration(b.budget_min * 60)} hedef`}
                            {over && ' ✓'}
                          </span>
                        </div>
                        <div className="relative h-2 rounded-full bg-slate-100">
                          <div className="h-2 rounded-full" style={{ width: `${(b.tracked_min / maxBoard) * 100}%`, backgroundColor: b.color }} />
                          {b.budget_min != null && (
                            <div className="absolute -top-1 h-4 w-0.5 bg-slate-700" style={{ left: `${(b.budget_min / maxBoard) * 100}%` }} title="Hedef" />
                          )}
                        </div>
                      </li>
                    )
                  })}
              </ul>
            </Panel>

            <Panel title="Ruh hâli ve enerji (1–5)">
              {moods.length === 0 ? (
                <Empty height={220}>Gün sonu değerlendirmesinde ruh hâlini ve enerjini girdikçe burada bir çizgi oluşur.</Empty>
              ) : (
                <ResponsiveContainer width="100%" height={220}>
                  <LineChart data={daily} margin={{ top: 8, right: 16, left: -20, bottom: 0 }}>
                    <CartesianGrid vertical={false} stroke={GRID} strokeDasharray="3 4" />
                    <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                    <YAxis domain={[1, 5]} ticks={[1, 2, 3, 4, 5]} tick={AXIS} tickLine={false} axisLine={false} />
                    <Tooltip content={<ChartTip />} />
                    <Legend wrapperStyle={{ fontSize: 12 }} iconType="circle" formatter={legendText} />
                    <Line dataKey="mood" name="Ruh hâli" stroke={C.s1} strokeWidth={2} dot={{ r: 4, strokeWidth: 2, stroke: SURFACE, fill: C.s1 }} activeDot={{ r: 5, strokeWidth: 2, stroke: SURFACE, fill: C.s1 }} connectNulls />
                    <Line dataKey="energy" name="Enerji" stroke={C.s2} strokeWidth={2} dot={{ r: 4, strokeWidth: 2, stroke: SURFACE, fill: C.s2 }} activeDot={{ r: 5, strokeWidth: 2, stroke: SURFACE, fill: C.s2 }} connectNulls />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </Panel>
          </div>

          <div className="grid gap-x-10 gap-y-10 lg:grid-cols-3">
            <Panel title="En verimli saatler (dakika)">
              {!anyTime ? (
                <Empty height={200}>Süre kaydettikçe dolacak.</Empty>
              ) : (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={hours} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
                  <CartesianGrid vertical={false} stroke={GRID} strokeDasharray="3 4" />
                  <XAxis dataKey="hour" tick={AXIS} tickLine={false} axisLine={false} interval={2} />
                  <YAxis tick={AXIS} tickLine={false} axisLine={false} />
                  <Tooltip content={<ChartTip unit="min" />} cursor={CURSOR} labelFormatter={(h) => `${h}:00–${h}:59`} />
                  <Bar dataKey="minutes" name="Süre" fill={C.s1} radius={BAR_RADIUS} />
                </BarChart>
              </ResponsiveContainer>
              )}
            </Panel>

            <Panel title="Haftanın günleri (dakika)">
              {!anyTime ? (
                <Empty height={200}>Süre kaydettikçe dolacak.</Empty>
              ) : (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={weekdays} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
                  <CartesianGrid vertical={false} stroke={GRID} strokeDasharray="3 4" />
                  <XAxis dataKey="day" tick={AXIS} tickLine={false} axisLine={false} />
                  <YAxis tick={AXIS} tickLine={false} axisLine={false} />
                  <Tooltip content={<ChartTip unit="min" />} cursor={CURSOR} />
                  <Bar dataKey="minutes" name="Süre" fill={C.s1} radius={BAR_RADIUS} />
                </BarChart>
              </ResponsiveContainer>
              )}
            </Panel>

            <Panel title="Dikkat çekenler">
              <h3 className="mb-1 text-[14px] font-semibold text-slate-700">En çok ertelenenler</h3>
              {s.most_postponed.length === 0 ? (
                <p className="mb-3 text-[14px] text-slate-500">Bu aralıkta ertelenen iş yok.</p>
              ) : (
                <ul className="mb-3 space-y-1 text-sm">
                  {s.most_postponed.map((p) => (
                    <li key={p.card_id} className="flex justify-between gap-2"><span className="truncate">{p.title}</span><span className="text-slate-500 tabular-nums">{p.count}×</span></li>
                  ))}
                </ul>
              )}
              <h3 className="mb-1 text-[14px] font-semibold text-slate-700">Tahmini en çok aşanlar</h3>
              {(acc?.biggest_overruns ?? []).length === 0 ? (
                <p className="text-[14px] text-slate-500">Tahmini ve süresi olan bir kart tamamlandığında görünür.</p>
              ) : (
                <ul className="space-y-1 text-sm">
                  {acc!.biggest_overruns.map((o) => (
                    <li key={o.card_id} className="flex justify-between gap-2" title={`${o.tracked_min} dk / ${o.estimated_min} dk tahmin`}>
                      <span className="truncate">{o.title}</span>
                      <span className="text-slate-500 tabular-nums">×{o.ratio.toFixed(1)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          </div>
          </div>
        </>
      )}
    </div>
  )
}
