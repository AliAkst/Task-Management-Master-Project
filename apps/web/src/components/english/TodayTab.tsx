import { useCallback, useEffect, useRef, useState } from 'react'
import { Check } from 'lucide-react'
import { CATEGORY_LABELS, useEnglishToday, useReviewVocab, type Vocab } from '../../api/english'
import SpeakButton from './SpeakButton'

const GRADES = ['Bilmedim', 'Yanlış', 'Neredeyse', 'Zor', 'İyi', 'Kolay']

function VocabCard({ vocab, onGraded }: { vocab: Vocab; onGraded: () => void }) {
  const review = useReviewVocab()
  const [shown, setShown] = useState(false)
  const busy = useRef(false) // hizli cift tus: gonderilirken yok sayilir

  const grade = useCallback(
    (g: number) => {
      if (busy.current) return
      busy.current = true
      review.mutate(
        { id: vocab.id, grade: g },
        {
          onSuccess: () => {
            setShown(false)
            onGraded()
          },
          onSettled: () => {
            busy.current = false
          },
        },
      )
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [vocab.id],
  )

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable)) return
      if (e.ctrlKey || e.metaKey || e.altKey) return
      if (e.key === ' ') {
        e.preventDefault()
        setShown(true)
      } else if (shown && /^[0-5]$/.test(e.key)) {
        grade(Number(e.key))
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [shown, grade])

  return (
    <div className="rounded-xl border border-slate-200 bg-surface p-5">
      <div className="flex items-center gap-2">
        <p className="text-2xl font-semibold">{vocab.term}</p>
        <SpeakButton text={vocab.term} label={`${vocab.term} seslendir`} />
      </div>
      {!shown ? (
        <button
          onClick={() => setShown(true)}
          className="mt-4 rounded-md bg-slate-900 px-3 py-1.5 text-[15px] text-on-ink"
        >
          Anlamı göster <span className="text-xs opacity-70">(Boşluk)</span>
        </button>
      ) : (
        <div className="mt-3">
          <p className="text-lg">{vocab.meaning_tr}</p>
          {vocab.example && <p className="mt-1 text-[15px] text-slate-600 italic">{vocab.example}</p>}
          <div className="mt-4 grid grid-cols-3 gap-2 sm:grid-cols-6">
            {GRADES.map((label, g) => (
              <button
                key={g}
                disabled={review.isPending}
                onClick={() => grade(g)}
                className="rounded-md border border-slate-300 bg-surface px-1 py-1.5 text-sm hover:bg-slate-100 disabled:opacity-50"
              >
                <span className="block text-xs text-slate-500">{g}</span>
                {label}
              </button>
            ))}
          </div>
          {review.isError && (
            <p role="alert" className="mt-2 text-sm text-red-700">
              Kaydedilemedi, tekrar dene
            </p>
          )}
        </div>
      )}
    </div>
  )
}

export default function TodayTab({ onPractice }: { onPractice: () => void }) {
  const today = useEnglishToday()
  const [graded, setGraded] = useState<number[]>([])

  if (today.isPending) return <p className="text-slate-600">Yükleniyor…</p>
  if (today.isError || !today.data) return <p role="alert" className="text-red-700">Bugün yüklenemedi.</p>
  const d = today.data
  // Notlanan kart, liste yenilenene kadar da gizlenir (ayni karta ikinci not gitmesin).
  const queue = d.due_vocab.filter((v) => !graded.includes(v.id))
  const current = queue[0]

  return (
    <div className="space-y-6">
      {d.task && (
        <div className="rounded-xl border border-slate-200 bg-surface p-4">
          <p className="text-sm text-slate-500">Bugünün görevi</p>
          <p className="mt-1 text-[16px]">{d.task}</p>
        </div>
      )}

      <section aria-label="Kelime tekrarı">
        <h2 className="mb-3 text-[20px]">Kelime tekrarı</h2>
        {current ? (
          <>
            <p className="mb-2 text-sm text-slate-600">{queue.length} kelime bekliyor</p>
            <VocabCard key={current.id} vocab={current} onGraded={() => setGraded((g) => [...g, current.id])} />
          </>
        ) : (
          <p className="flex items-center gap-2 rounded-xl border border-slate-200 bg-surface p-4">
            <Check size={16} aria-hidden />
            {graded.length > 0 || d.practiced_today ? 'Bugünlük tekrar bitti' : 'Bugün vadesi gelen kelime yok'}
          </p>
        )}
      </section>

      {d.top_categories.length > 0 && (
        <section aria-label="En sık hatalar">
          <h2 className="mb-2 text-[20px]">En sık hatalar</h2>
          <div className="flex flex-wrap gap-2">
            {d.top_categories.slice(0, 3).map((c) => (
              <span key={c.category} className="rounded-full border border-slate-300 px-3 py-0.5 text-sm">
                {CATEGORY_LABELS[c.category] ?? c.category} · {c.count}
              </span>
            ))}
          </div>
        </section>
      )}

      <button onClick={onPractice} className="rounded-md bg-slate-900 px-4 py-1.5 text-[15px] text-on-ink">
        Pratik yap
      </button>
    </div>
  )
}
