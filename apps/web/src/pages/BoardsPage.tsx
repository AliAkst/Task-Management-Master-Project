import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useBoards, useCreateBoard } from '../api/boards'
import BoardForm from '../components/BoardForm'
import Modal from '../components/Modal'
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

  const existing = new Set(boards.data?.map((b) => b.name))
  const suggestions = SUGGESTED.filter((s) => !existing.has(s.name))

  return (
    <div className="mx-auto w-full max-w-5xl p-6">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Board'lar</h1>
        <button
          onClick={() => setOpen(true)}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white"
        >
          + Yeni board
        </button>
      </div>

      {boards.isLoading && <p className="text-slate-500">Yükleniyor…</p>}
      {boards.error && <p className="text-red-600">{boards.error.message}</p>}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {boards.data?.map((b) => (
          <Link
            key={b.id}
            to={`/boards/${b.id}`}
            className="group rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200 transition hover:shadow-md"
          >
            <div className="mb-2 h-1.5 w-12 rounded-full" style={{ backgroundColor: b.color }} />
            <div className="flex items-center gap-2">
              <h2 className="font-medium group-hover:underline">{b.name}</h2>
              {b.privacy === 'local_only' && (
                <span title="Sadece local model görebilir" className="text-xs">🔒</span>
              )}
            </div>
            {b.scope_description && (
              <p className="mt-1 line-clamp-2 text-sm text-slate-500">{b.scope_description}</p>
            )}
            <p className="mt-3 text-xs text-slate-500">{b.open_card_count} açık kart</p>
          </Link>
        ))}
      </div>

      {boards.data && suggestions.length > 0 && (
        <section className="mt-10">
          <h2 className="mb-3 text-sm font-medium text-slate-600">Önerilen alanlar</h2>
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
