import { useState, type FormEvent } from 'react'
import { Lock, LockOpen, Plus, Sparkles, Trash2, User, Bot } from 'lucide-react'
import { useBoards } from '../api/boards'
import { useFactMutations, useFacts, useGoalMutations, useGoals, type Fact, type GoalStatus } from '../api/profile'
import { useAssistantUi } from '../stores/assistant'

const GOAL_STATUS: Record<GoalStatus, string> = {
  active: 'Devam ediyor',
  achieved: 'Ulaşıldı',
  dropped: 'Bırakıldı',
}

const ACQUAINT_MESSAGE =
  'Merhaba! Beni daha iyi tanıman için bana birkaç soru sorar mısın? Her seferinde bir soru sor.'

function FactRow({ fact }: { fact: Fact }) {
  const m = useFactMutations()
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(fact.content)

  function save() {
    setEditing(false)
    const v = value.trim()
    if (v && v !== fact.content) m.update.mutate({ id: fact.id, content: v })
    else setValue(fact.content)
  }

  return (
    <li className="group flex items-start gap-2 py-1.5">
      <span className="mt-1 text-slate-400" title={fact.source === 'ai_learned' ? 'Asistan öğrendi' : 'Sen ekledin'}>
        {fact.source === 'ai_learned' ? <Bot size={14} aria-label="Asistan öğrendi" /> : <User size={14} aria-label="Sen ekledin" />}
      </span>
      {editing ? (
        <input
          autoFocus
          className="min-w-0 flex-1 rounded border border-slate-300 px-2 py-0.5 text-[15px]"
          value={value}
          maxLength={500}
          onChange={(e) => setValue(e.target.value)}
          onBlur={save}
          onKeyDown={(e) => {
            if (e.key === 'Enter') save()
            if (e.key === 'Escape') {
              setValue(fact.content)
              setEditing(false)
            }
          }}
        />
      ) : (
        <button onClick={() => setEditing(true)} className="min-w-0 flex-1 text-left text-[15px] hover:text-blue-700" title="Düzeltmek için tıkla">
          {fact.content}
        </button>
      )}
      <button
        onClick={() => m.update.mutate({ id: fact.id, is_private: !fact.is_private })}
        className={`rounded p-1 ${fact.is_private ? 'text-slate-700' : 'text-slate-300 group-hover:text-slate-500'} hover:bg-slate-100`}
        title={fact.is_private ? 'Sadece local model görüyor (bulut modellere gönderilmez)' : 'Tüm modeller görebilir — sadece local yap'}
        aria-label={fact.is_private ? 'Gizliliği kaldır' : 'Sadece local yap'}
      >
        {fact.is_private ? <Lock size={14} /> : <LockOpen size={14} />}
      </button>
      <button
        onClick={() => confirm('Bu bilgi silinsin mi?') && m.remove.mutate(fact.id)}
        className="rounded p-1 text-slate-300 group-hover:text-slate-500 hover:bg-slate-100 hover:text-red-700"
        aria-label="Sil"
      >
        <Trash2 size={14} />
      </button>
    </li>
  )
}

function FactsSection() {
  const facts = useFacts()
  const m = useFactMutations()
  const [category, setCategory] = useState('personal')
  const [content, setContent] = useState('')

  function add(e: FormEvent) {
    e.preventDefault()
    if (!content.trim()) return
    m.create.mutate({ category, content: content.trim() }, { onSuccess: () => setContent('') })
  }

  if (facts.error) return <p className="text-red-700">{facts.error.message} (asistan servisi çalışıyor mu?)</p>
  if (!facts.data) return <p className="text-slate-500">Yükleniyor…</p>
  const { categories, facts: list } = facts.data

  return (
    <section>
      <h2 className="text-[22px]">Seninle ilgili bildiklerim</h2>
      <p className="mt-1 mb-4 max-w-prose text-[15px] text-slate-600">
        Asistan bunları planlarken kullanır. Yanlış olanı üzerine tıklayıp düzelt; kilitli olanlar bulut modellere gönderilmez.
      </p>
      {list.length === 0 && (
        <p className="mb-4 text-[15px] text-slate-500">Henüz bir şey bilmiyorum. Tanışma sohbetini başlat ya da aşağıdan kendin ekle.</p>
      )}
      <div className="space-y-4">
        {categories
          .filter((c) => list.some((f) => f.category === c.key))
          .map((c) => (
            <div key={c.key}>
              <h3 className="border-b border-slate-200 pb-1 text-[14px] font-semibold text-slate-700">
                {c.label}
                {c.private_by_default && <span className="ml-2 font-normal text-slate-500">varsayılan olarak gizli</span>}
              </h3>
              <ul>{list.filter((f) => f.category === c.key).map((f) => <FactRow key={f.id} fact={f} />)}</ul>
            </div>
          ))}
      </div>
      <form onSubmit={add} className="mt-5 flex flex-wrap gap-2">
        <select className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm" value={category} onChange={(e) => setCategory(e.target.value)}>
          {categories.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
        </select>
        <input
          className="min-w-48 flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm"
          placeholder="Kendin hakkında bir şey ekle (ör. Akşamları daha verimliyim)"
          maxLength={500}
          value={content}
          onChange={(e) => setContent(e.target.value)}
        />
        <button disabled={!content.trim() || m.create.isPending} className="inline-flex items-center gap-1 rounded-md bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-40">
          <Plus size={15} aria-hidden /> Ekle
        </button>
      </form>
    </section>
  )
}

function GoalsSection() {
  const goals = useGoals()
  const boards = useBoards()
  const m = useGoalMutations()
  const [title, setTitle] = useState('')
  const [why, setWhy] = useState('')
  const [target, setTarget] = useState('')
  const [boardId, setBoardId] = useState('')
  const boardName = new Map((boards.data ?? []).map((b) => [b.id, b]))

  function add(e: FormEvent) {
    e.preventDefault()
    if (!title.trim()) return
    m.create.mutate(
      { title: title.trim(), why: why.trim() || null, target_date: target || null, board_id: boardId ? Number(boardId) : null },
      { onSuccess: () => { setTitle(''); setWhy(''); setTarget(''); setBoardId('') } },
    )
  }

  const list = goals.data ?? []
  const ordered = [...list].sort((a, b) => Number(a.status !== 'active') - Number(b.status !== 'active'))

  return (
    <section>
      <h2 className="text-[22px]">Hedeflerin</h2>
      <p className="mt-1 mb-4 max-w-prose text-[15px] text-slate-600">
        Hayatında yapmak istediklerin. Asistan planı bunlara göre şekillendirir.
      </p>
      {list.length === 0 && <p className="mb-4 text-[15px] text-slate-500">Henüz hedef yok.</p>}
      <ul className="space-y-3">
        {ordered.map((g) => {
          const board = g.board_id != null ? boardName.get(g.board_id) : undefined
          return (
            <li key={g.id} className={`relative rounded-md border border-slate-200 bg-white py-3 pr-3 pl-5 ${g.status !== 'active' ? 'opacity-60' : ''}`}>
              <span aria-hidden className="absolute inset-y-0 left-0 w-1.5 rounded-l-md" style={{ backgroundColor: board?.color ?? 'var(--color-slate-300)' }} />
              <div className="flex flex-wrap items-baseline gap-x-3">
                <p className={`flex-1 text-[16px] font-semibold ${g.status === 'achieved' ? 'line-through decoration-slate-400' : ''}`}>{g.title}</p>
                <select
                  className="rounded border border-slate-200 bg-white px-1.5 py-0.5 text-xs"
                  value={g.status}
                  onChange={(e) => m.update.mutate({ id: g.id, status: e.target.value as GoalStatus })}
                  aria-label="Hedef durumu"
                >
                  {(Object.keys(GOAL_STATUS) as GoalStatus[]).map((s) => <option key={s} value={s}>{GOAL_STATUS[s]}</option>)}
                </select>
                <button onClick={() => confirm('Hedef silinsin mi?') && m.remove.mutate(g.id)} className="text-slate-400 hover:text-red-700" aria-label="Hedefi sil">
                  <Trash2 size={14} />
                </button>
              </div>
              {g.why && <p className="mt-1 text-[14px] text-slate-600">{g.why}</p>}
              <p className="mt-1 text-[13px] text-slate-500">
                {[board?.name, g.target_date && `Hedef tarih: ${new Date(g.target_date).toLocaleDateString('tr-TR', { day: 'numeric', month: 'long', year: 'numeric' })}`, g.created_by === 'ai' && 'asistan önerdi']
                  .filter(Boolean)
                  .join(', ')}
              </p>
            </li>
          )
        })}
      </ul>
      <form onSubmit={add} className="mt-5 grid gap-2 rounded-md border border-dashed border-slate-300 p-3 sm:grid-cols-2">
        <input className="rounded-md border border-slate-300 px-3 py-1.5 text-sm sm:col-span-2" placeholder="Yeni hedef (ör. Mart'a kadar Docker sertifikası)" maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} />
        <input className="rounded-md border border-slate-300 px-3 py-1.5 text-sm sm:col-span-2" placeholder="Neden önemli? (opsiyonel)" maxLength={5000} value={why} onChange={(e) => setWhy(e.target.value)} />
        <input type="date" className="rounded-md border border-slate-300 px-2 py-1.5 text-sm" value={target} onChange={(e) => setTarget(e.target.value)} aria-label="Hedef tarih" />
        <select className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm" value={boardId} onChange={(e) => setBoardId(e.target.value)} aria-label="İlgili alan">
          <option value="">İlgili alan (opsiyonel)</option>
          {boards.data?.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
        </select>
        <button disabled={!title.trim() || m.create.isPending} className="inline-flex items-center justify-center gap-1 rounded-md bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-40 sm:col-span-2 sm:justify-self-end">
          <Plus size={15} aria-hidden /> Hedef ekle
        </button>
      </form>
    </section>
  )
}

export default function ProfilePage() {
  const startConversation = useAssistantUi((s) => s.startConversation)
  return (
    <div className="mx-auto w-full max-w-5xl p-4 sm:p-6">
      <header className="mb-8 flex flex-wrap items-end gap-4 border-b border-slate-200 pb-4">
        <div>
          <h1 className="text-[44px] leading-[1.05]">Profil</h1>
          <p className="mt-1 text-[15px] text-slate-600">Asistanın seni ne kadar tanıdığı ve neye ulaşmak istediğin.</p>
        </div>
        <button
          onClick={() => startConversation(ACQUAINT_MESSAGE)}
          className="ml-auto inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-[15px] text-white hover:bg-slate-700"
        >
          <Sparkles size={16} aria-hidden /> Tanışma sohbetini başlat
        </button>
      </header>
      <div className="grid gap-10 lg:grid-cols-2">
        <GoalsSection />
        <FactsSection />
      </div>
    </div>
  )
}
