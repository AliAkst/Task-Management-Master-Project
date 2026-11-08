import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useBoards, useCreateBoard } from '../api/boards'
import { Lock, Plus, Sparkles, Target } from 'lucide-react'
import { useModels } from '../api/assistant'
import BoardForm from '../components/BoardForm'
import Modal from '../components/Modal'
import { PageHeader } from '../components/Page'
import type { BoardCreate } from '../lib/types'

// Ilk acilista tek tikla olusturulabilecek hayat alanlari
const SUGGESTED: BoardCreate[] = [
  { name: 'Spor', color: '#22c55e', scope_description: 'Antrenman, koşu, beslenme ve sağlıkla ilgili işler.' },
  { name: 'İş', color: '#3b82f6', scope_description: 'İşle ilgili görevler, toplantılar ve projeler.' },
  { name: 'Date planları', color: '#ec4899', privacy: 'local_only', scope_description: 'Sevgilimle buluşma ve etkinlik planları.' },
  { name: 'Günlük işler', color: '#eab308', scope_description: 'Ev toparlama, alışveriş, faturalar gibi rutin işler.' },
  { name: 'Eğitimler', color: '#6366f1', scope_description: 'İş için ilerletmek istediğim kurslar ve eğitimler.' },
  { name: 'Fikirler', color: '#a855f7', scope_description: 'Aklıma gelen fikirler ve ileride yapılacaklar.' },
]

export default function BoardsPage() {
  const boards = useBoards()
  const create = useCreateBoard()
  const [open, setOpen] = useState(false)

  const models = useModels()
  const modelLabel = (id: string) => models.data?.models.find((m) => m.id === id)?.label ?? id.replace('ollama:', '')
  const existing = new Set(boards.data?.map((b) => b.name))
  const suggestions = SUGGESTED.filter((s) => !existing.has(s.name))

  return (
    <div className="mx-auto w-full max-w-6xl p-4 sm:p-6">
      <PageHeader
        title="Board'lar"
        subtitle="Hayatının alanları. Asistan gelen işleri her board'un tarifine bakarak doğru yere koyar."
        actions={
          <button onClick={() => setOpen(true)} className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-4 py-2 text-[15px] text-white hover:bg-slate-700">
            <Plus size={16} aria-hidden /> Yeni board
          </button>
        }
      />

      {boards.isLoading && <p className="text-slate-500">Yükleniyor…</p>}
      {boards.error && <p className="text-red-600">{boards.error.message}</p>}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {boards.data?.map((b) => (
          <Link
            key={b.id}
            to={`/boards/${b.id}`}
            className="group relative overflow-hidden rounded-lg border border-slate-200 bg-white py-4 pr-4 pl-7 hover:border-slate-400"
          >
            <span aria-hidden className="absolute inset-y-0 left-0 w-2.5" style={{ backgroundColor: b.color }} />
            <h2 className="text-[20px] group-hover:underline">{b.name}</h2>
            {b.scope_description && (
              <p className="mt-1 line-clamp-2 text-[14px] text-slate-600">{b.scope_description}</p>
            )}
            <p className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px] text-slate-600">
              <span className="font-semibold text-slate-900 tabular-nums">{b.open_card_count} açık kart</span>
              {b.weekly_time_budget_min != null && b.weekly_time_budget_min > 0 && (
                <span className="inline-flex items-center gap-1"><Target size={12} aria-hidden /> Haftada {Math.round((b.weekly_time_budget_min / 60) * 10) / 10} saat</span>
              )}
              {b.privacy === 'local_only' && (
                <span className="inline-flex items-center gap-1"><Lock size={12} aria-hidden /> Sadece local</span>
              )}
              {b.default_model_id && (
                <span className="inline-flex items-center gap-1"><Sparkles size={12} aria-hidden /> {modelLabel(b.default_model_id)}</span>
              )}
            </p>
          </Link>
        ))}
      </div>

      {boards.data && suggestions.length > 0 && (
        <section className="mt-10">
          <h2 className="text-[22px]">Önerilen alanlar</h2>
          <p className="mt-1 mb-3 text-[15px] text-slate-600">Tek tıkla ekle; sonra adını ve tarifini değiştirebilirsin.</p>
          <div className="flex flex-wrap gap-2">
            {suggestions.map((s) => (
              <button
                key={s.name}
                disabled={create.isPending}
                onClick={() => create.mutate(s)}
                className="rounded-full border border-dashed border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:border-slate-500 disabled:opacity-50"
              >
                <span className="mr-1.5 inline-block h-2 w-2 rounded-full" style={{ backgroundColor: s.color }} />
                {s.name}
              </button>
            ))}
          </div>
        </section>
      )}

      {open && (
        <Modal title="Yeni board" onClose={() => setOpen(false)}>
          <BoardForm
            submitLabel="Oluştur"
            busy={create.isPending}
            onCancel={() => setOpen(false)}
            onSubmit={(data) => create.mutate(data, { onSuccess: () => setOpen(false) })}
          />
          {create.error && <p className="mt-2 text-sm text-red-600">{create.error.message}</p>}
        </Modal>
      )}
    </div>
  )
}
