import { Play } from 'lucide-react'
import { courseErrorText, useCourseMutations, useCourses } from '../api/learning'
import { useSessionMutations } from '../api/sessions'
import type { Course } from '../lib/types'

const etaFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'long' })
const etaLabel = (iso: string) => {
  const [y, m, d] = iso.split('-').map(Number)
  return etaFmt.format(new Date(y, m - 1, d))
}

/** Tek kurs: ilerleme, siradaki parca, hiz, tahmini bitis. */
function CourseRow({ course }: { course: Course }) {
  const { setStatus } = useCourseMutations()
  const { start } = useSessionMutations()
  const paused = course.status === 'paused'
  const pct = course.parts_total ? Math.round((course.parts_done / course.parts_total) * 100) : 0
  // G3: gonderilirken kilitli (isPending), onSettled'da acilir
  const busy = setStatus.isPending || start.isPending
  const error = setStatus.error ?? start.error

  return (
    <li className="py-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h3 className="text-[16px] font-semibold text-slate-900">{course.title}</h3>
        <span
          className={`rounded-full px-2 py-0.5 text-[12px] ${paused ? 'bg-slate-200 text-slate-600' : 'bg-emerald-100 text-emerald-800'}`}
        >
          {paused ? 'duraklatıldı' : 'aktif'}
        </span>
        <button
          type="button"
          disabled={busy}
          onClick={() => setStatus.mutate({ goalId: course.goal_id, status: paused ? 'active' : 'paused' })}
          className="ml-auto text-[13px] text-blue-700 hover:underline disabled:opacity-50"
        >
          {paused ? 'Aktif et' : 'Duraklat'}
        </button>
      </div>

      <div className="mt-2 flex items-center gap-3">
        <div
          role="progressbar"
          aria-label={`${course.title} ilerlemesi`}
          aria-valuemin={0}
          aria-valuemax={course.parts_total}
          aria-valuenow={course.parts_done}
          className="h-2 flex-1 overflow-hidden rounded-full bg-slate-200"
        >
          <div className="h-full bg-slate-700" style={{ width: `${pct}%` }} />
        </div>
        <span className="text-[13px] tabular-nums text-slate-600">
          {course.parts_done}/{course.parts_total} parça
        </span>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[14px] text-slate-700">
        {course.next_part ? (
          <span className="inline-flex items-center gap-2">
            Sıradaki: <strong className="font-semibold">{course.next_part.title}</strong>
            <button
              type="button"
              disabled={busy}
              onClick={() => start.mutate(course.next_part!.id)}
              className="inline-flex items-center gap-1 rounded-md bg-slate-900 px-2 py-0.5 text-[13px] text-on-ink hover:bg-slate-700 disabled:opacity-50"
            >
              <Play size={12} aria-hidden /> Başla
            </button>
          </span>
        ) : (
          <span>Tüm parçalar tamamlandı</span>
        )}
        <span>
          {course.velocity_per_week
            ? `Haftada ${String(course.velocity_per_week).replace('.', ',')} parça`
            : 'Hız verisi yok'}
        </span>
        {course.eta_reason === 'ok' && course.eta_date ? (
          <span>Tahmini bitiş: {etaLabel(course.eta_date)}</span>
        ) : course.eta_reason === 'no_velocity' ? (
          <span className="text-slate-500">Tahmini bitiş için hız verisi yok</span>
        ) : null}
      </div>
      {error && (
        <p role="alert" className="mt-1 text-[13px] text-red-700">
          {courseErrorText(error)}
        </p>
      )}
    </li>
  )
}

/** İstatistik sayfasi: Kurslarim (en cok 2 aktif kurs). */
export default function CoursesSection() {
  const q = useCourses('active')
  return (
    <section className="mb-10 border-t border-slate-300 pt-3">
      <h2 className="mb-1 text-[18px]">Kurslarım</h2>
      {q.isLoading && <p className="text-[14px] text-slate-500">Yükleniyor…</p>}
      {q.error && <p className="text-[14px] text-red-700">{courseErrorText(q.error)}</p>}
      {q.data && q.data.length === 0 && (
        <p className="text-[14px] text-slate-500">
          Henüz takip edilen kurs yok. Alt parçalara bölünmüş bir kartı açıp “Kurs olarak takip et”i seç.
        </p>
      )}
      {q.data && q.data.length > 0 && (
        <ul className="divide-y divide-slate-200">
          {q.data.map((c) => (
            <CourseRow key={c.goal_id} course={c} />
          ))}
        </ul>
      )}
    </section>
  )
}
