import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { CATEGORY_LABELS, useEnglishProgress } from '../../api/english'
import { useThemeColors } from '../../hooks/useThemeColors'

const BAR_RADIUS: [number, number, number, number] = [4, 4, 0, 0]

export default function ProgressTab() {
  const q = useEnglishProgress()
  const tc = useThemeColors()
  const AXIS = { fontSize: 12, fill: tc.axis }

  if (q.isPending) return <p className="text-slate-600">Yükleniyor…</p>
  if (q.isError || !q.data) return <p role="alert" className="text-red-700">İlerleme yüklenemedi.</p>
  const p = q.data

  const weeks = p.weekly_minutes.map((w) => ({ week: w.week, minutes: w.minutes }))
  const cats = Array.from(new Set(p.mistakes_by_category.map((m) => m.category)))
  const byWeek = new Map<string, Record<string, number | string>>()
  for (const m of p.mistakes_by_category) {
    const row = byWeek.get(m.week) ?? { week: m.week }
    row[m.category] = m.count
    byWeek.set(m.week, row)
  }
  const catRows = [...byWeek.values()].sort((a, b) => String(a.week).localeCompare(String(b.week)))
  const palette = [tc.s1, tc.s2, tc.s3, tc.s4]

  const empty =
    p.streak_days === 0 && p.vocab_stats.total === 0 && weeks.every((w) => w.minutes === 0) && cats.length === 0
  if (empty) return <p className="text-slate-600">Henüz veri yok</p>

  return (
    <div className="space-y-8">
      <div>
        <p className="text-5xl font-semibold tabular-nums">{p.streak_days}</p>
        <p className="text-sm text-slate-600">gün üst üste</p>
      </div>

      <section aria-label="Haftalık dakika">
        <h2 className="mb-2 text-[20px]">Haftalık dakika</h2>
        {weeks.every((w) => w.minutes === 0) ? (
          <p className="text-slate-600">Henüz veri yok</p>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={weeks} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke={tc.grid} strokeDasharray="3 4" />
              <XAxis dataKey="week" tick={AXIS} tickLine={false} axisLine={false} />
              <YAxis allowDecimals={false} tick={AXIS} tickLine={false} axisLine={false} />
              <Tooltip cursor={{ fill: tc.cursor }} />
              <Bar dataKey="minutes" name="Dakika" fill={tc.s1} radius={BAR_RADIUS} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </section>

      <section aria-label="Kelime durumu">
        <h2 className="mb-2 text-[20px]">Kelimeler</h2>
        <dl className="grid max-w-md grid-cols-3 gap-3 text-center">
          {[
            ['Toplam', p.vocab_stats.total],
            ['Vadesi gelen', p.vocab_stats.due],
            ['Oturmuş', p.vocab_stats.mature],
          ].map(([label, n]) => (
            <div key={label} className="rounded-xl border border-slate-200 bg-surface p-3">
              <dd className="text-2xl font-semibold tabular-nums">{n}</dd>
              <dt className="text-xs text-slate-600">{label}</dt>
            </div>
          ))}
        </dl>
      </section>

      <section aria-label="Hata kategorisi eğilimi">
        <h2 className="mb-2 text-[20px]">Hata kategorileri</h2>
        {catRows.length === 0 ? (
          <p className="text-slate-600">Henüz veri yok</p>
        ) : (
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={catRows} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke={tc.grid} strokeDasharray="3 4" />
              <XAxis dataKey="week" tick={AXIS} tickLine={false} axisLine={false} />
              <YAxis allowDecimals={false} tick={AXIS} tickLine={false} axisLine={false} />
              <Tooltip cursor={{ fill: tc.cursor }} />
              <Legend
                wrapperStyle={{ fontSize: 12 }}
                iconType="circle"
                formatter={(v: string) => <span style={{ color: tc.legend }}>{CATEGORY_LABELS[v] ?? v}</span>}
              />
              {cats.map((c, i) => (
                <Bar
                  key={c}
                  dataKey={c}
                  name={c}
                  stackId="c"
                  fill={palette[i % palette.length]}
                  stroke={tc.paper}
                  strokeWidth={2}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        )}
      </section>
    </div>
  )
}
