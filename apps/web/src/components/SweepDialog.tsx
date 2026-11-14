import { useMemo, useState } from 'react'
import { useBoard, useBoardMutations } from '../api/boards'
import { useBulkCards, useSweepCandidates, type SweepCard } from '../api/sweep'
import { ApiError } from '../lib/api'
import Modal from './Modal'

type Action = 'archive' | 'complete' | 'none'
type Phase = 'select' | 'confirm' | 'sending' | 'done'

const CHUNK = 200
const ACTIONS: { value: Action; label: string }[] = [
  { value: 'archive', label: 'Arşivle' },
  { value: 'complete', label: 'Tamamlandı say' },
  { value: 'none', label: 'Dokunma' },
]
const dueFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short', year: 'numeric' })

interface ViewGroup {
  key: string
  label: string
  cards: SweepCard[]
  defaultAction: Action
}

const chunks = (ids: number[]) => {
  const out: number[][] = []
  for (let i = 0; i < ids.length; i += CHUNK) out.push(ids.slice(i, i + CHUNK))
  return out
}

const errText = (e: unknown) => (e instanceof ApiError ? e.message : 'Ulaşılamadı')

/** Eski kart süpürme sihirbazı (Faz 13h1): gruplar, onay kutuları, toplu arşiv / tamamlandı. */
export default function SweepDialog({ boardId, onClose }: { boardId: number; onClose: () => void }) {
  const cand = useSweepCandidates(boardId)
  const board = useBoard(boardId)
  const { updateList } = useBoardMutations(boardId)
  const bulk = useBulkCards(boardId)

  const [picked, setPicked] = useState<Record<string, number[]>>({})
  const [actions, setActions] = useState<Record<string, Action>>({})
  const [accepted, setAccepted] = useState<number[]>([]) // "tamamlananlar listesi" onaylananlar
  const [dismissed, setDismissed] = useState<number[]>([])
  const [phase, setPhase] = useState<Phase>('select')
  const [progress, setProgress] = useState({ done: 0, total: 0 })
  const [outcome, setOutcome] = useState<{ archived: number[]; completed: number; error: string | null; undone: number | null } | null>(null)

  const groups = useMemo<ViewGroup[]>(() => {
    const base: ViewGroup[] = (cand.data?.groups ?? []).map((g) => ({ ...g, defaultAction: 'archive' }))
    const extra: ViewGroup[] = accepted.map((listId) => {
      const lst = board.data?.lists.find((l) => l.id === listId)
      return {
        key: `done_list_${listId}`,
        label: `Bu listedekileri tamamlandı say: «${lst?.name ?? listId}»`,
        defaultAction: 'complete' as Action,
        cards: (board.data?.cards ?? [])
          .filter((c) => c.list_id === listId && c.status !== 'completed' && !c.is_archived)
          .map((c) => ({
            id: c.id,
            title: c.title,
            list_name: lst?.name ?? '',
            due_date: c.due_date,
            reason: 'Tamamlananlar listesinde ama açık',
          })),
      }
    })
    return [...extra, ...base]
  }, [cand.data, accepted, board.data])

  const hints = (cand.data?.done_list_hints ?? []).filter(
    (h) => !dismissed.includes(h.list_id) && !accepted.includes(h.list_id),
  )

  const actionOf = (g: ViewGroup) => actions[g.key] ?? g.defaultAction

  // Kart tek islem alir (ilk gruptaki gecerli); ayni kart iki grupta secilirse mukerrer id gitmez
  const plan = useMemo(() => {
    const seen = new Set<number>()
    const out = { archive: [] as number[], complete: [] as number[] }
    for (const g of groups) {
      const act = actions[g.key] ?? g.defaultAction
      if (act === 'none') continue
      for (const id of picked[g.key] ?? []) {
        if (seen.has(id)) continue
        seen.add(id)
        out[act].push(id)
      }
    }
    return out
  }, [groups, picked, actions])
  const total = plan.archive.length + plan.complete.length

  const setGroupPicked = (key: string, ids: number[]) => setPicked((p) => ({ ...p, [key]: ids }))
  const toggleCard = (key: string, id: number) => {
    const cur = picked[key] ?? []
    setGroupPicked(key, cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id])
  }

  const acceptHint = (listId: number) =>
    updateList.mutate(
      { id: listId, is_done_list: true },
      { onSuccess: () => setAccepted((a) => [...a, listId]) },
    )

  const run = async () => {
    setPhase('sending')
    const jobs = [
      ...chunks(plan.archive).map((ids) => ({ ids, op: 'archive' as const })),
      ...chunks(plan.complete).map((ids) => ({ ids, op: 'complete' as const })),
    ]
    setProgress({ done: 0, total: jobs.length })
    const archived: number[] = []
    let completed = 0
    let error: string | null = null
    for (const [i, job] of jobs.entries()) {
      try {
        await bulk.mutateAsync(job)
        if (job.op === 'archive') archived.push(...job.ids)
        else completed += job.ids.length
        setProgress({ done: i + 1, total: jobs.length })
      } catch (e) {
        error = errText(e) // dur; islenen parcalar geri alinmaz
        break
      }
    }
    setOutcome({ archived, completed, error, undone: null })
    setPhase('done')
  }

  const undo = async () => {
    if (!outcome) return
    let n = 0
    let error: string | null = null
    for (const ids of chunks(outcome.archived)) {
      try {
        await bulk.mutateAsync({ ids, op: 'unarchive' })
        n += ids.length
      } catch (e) {
        error = errText(e)
        break
      }
    }
    setOutcome({ ...outcome, archived: [], undone: n, error })
  }

  const locked = phase === 'sending' || bulk.isPending
  const closeIfFree = () => {
    if (!locked) onClose()
  }
  const processed = (outcome?.archived.length ?? 0) + (outcome?.completed ?? 0)

  return (
    <Modal title="Eski kartları süpür" size="lg" onClose={closeIfFree}>
      {cand.isLoading && <p className="text-slate-500">Adaylar aranıyor…</p>}
      {cand.error && <p className="text-red-600">{cand.error.message}</p>}

      {phase === 'select' && cand.data && (
        <>
          {hints.map((h) => (
            <div key={h.list_id} className="mb-3 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-slate-800">
              «{h.name}» tamamlananlar listesi mi?
              <span className="ml-3 inline-flex gap-2">
                <button
                  disabled={updateList.isPending}
                  onClick={() => acceptHint(h.list_id)}
                  className="rounded-md bg-slate-900 px-2.5 py-1 text-on-ink disabled:opacity-50"
                >
                  Evet: listeyi tamamlanan listesi yap
                </button>
                <button
                  onClick={() => setDismissed((d) => [...d, h.list_id])}
                  className="rounded-md border border-slate-300 px-2.5 py-1 hover:border-slate-900"
                >
                  Hayır
                </button>
              </span>
              {updateList.error && <span className="ml-2 text-red-600">{errText(updateList.error)}</span>}
            </div>
          ))}

          {groups.length === 0 && <p className="text-slate-600">Süpürülecek eski kart bulunamadı.</p>}

          <div className="max-h-[55vh] space-y-5 overflow-y-auto pr-1">
            {groups.map((g) => {
              const sel = picked[g.key] ?? []
              return (
                <section key={g.key} aria-label={g.label}>
                  <div className="flex flex-wrap items-center gap-3 border-b border-slate-200 pb-1">
                    <h3 className="text-[15px] font-semibold">
                      {g.label} <span className="font-normal text-slate-500">({g.cards.length})</span>
                    </h3>
                    <button
                      className="text-sm text-blue-700 hover:underline"
                      onClick={() => setGroupPicked(g.key, sel.length === g.cards.length ? [] : g.cards.map((c) => c.id))}
                    >
                      {sel.length === g.cards.length ? 'Seçimi kaldır' : 'Hepsini seç'}
                    </button>
                    <select
                      aria-label={`${g.label} için işlem`}
                      className="ml-auto rounded-md border border-slate-300 bg-surface px-2 py-1 text-sm"
                      value={actionOf(g)}
                      onChange={(e) => setActions((a) => ({ ...a, [g.key]: e.target.value as Action }))}
                    >
                      {ACTIONS.map((a) => (
                        <option key={a.value} value={a.value}>{a.label}</option>
                      ))}
                    </select>
                  </div>
                  <ul className="mt-1 divide-y divide-slate-100">
                    {g.cards.map((c) => (
                      <li key={c.id}>
                        <label className="flex cursor-pointer items-start gap-2 py-1 text-sm">
                          <input type="checkbox" className="mt-1" checked={sel.includes(c.id)} onChange={() => toggleCard(g.key, c.id)} />
                          <span className="min-w-0 flex-1">
                            <span className="block truncate">{c.title}</span>
                            <span className="block truncate text-xs text-slate-500">
                              {c.list_name}
                              {c.due_date && ` · son tarih ${dueFmt.format(new Date(c.due_date))}`} · {c.reason}
                            </span>
                          </span>
                        </label>
                      </li>
                    ))}
                  </ul>
                </section>
              )
            })}
          </div>

          <div className="mt-4 flex items-center gap-3 border-t border-slate-200 pt-3">
            <p className="text-sm text-slate-700" role="status">
              Seçili: {plan.archive.length} kart → arşiv
              {plan.complete.length > 0 && `, ${plan.complete.length} kart → tamamlandı`}
            </p>
            <button onClick={onClose} className="ml-auto rounded-md px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-200">Kapat</button>
            <button
              disabled={total === 0 || locked}
              onClick={() => setPhase('confirm')}
              className="rounded-md bg-slate-900 px-3 py-1.5 text-sm text-on-ink disabled:opacity-50"
            >
              Uygula
            </button>
          </div>
        </>
      )}

      {phase === 'confirm' && (
        <div>
          <p className="text-[15px]">
            {[
              plan.archive.length > 0 && `${plan.archive.length} kart arşivlenecek`,
              plan.complete.length > 0 && `${plan.complete.length} kart tamamlandı sayılacak`,
            ]
              .filter(Boolean)
              .join(', ')}
            . Devam?
          </p>
          <p className="mt-1 text-sm text-slate-500">Arşivleme bu pencereden geri alınabilir; kalıcı silme yapılmaz.</p>
          <div className="mt-4 flex justify-end gap-3">
            <button onClick={() => setPhase('select')} className="rounded-md px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-200">Vazgeç</button>
            <button onClick={run} className="rounded-md bg-slate-900 px-3 py-1.5 text-sm text-on-ink">Evet, uygula</button>
          </div>
        </div>
      )}

      {phase === 'sending' && (
        <p role="status" className="py-6 text-center text-slate-700">
          Uygulanıyor… {progress.done}/{progress.total}
        </p>
      )}

      {phase === 'done' && outcome && (
        <div role="status">
          {outcome.error ? (
            <p className="text-red-600">
              {processed} kart işlendi, kalanlar işlenmedi: {outcome.error}
            </p>
          ) : (
            <p className="text-[15px]">
              {[
                outcome.archived.length > 0 && `${outcome.archived.length} kart arşivlendi`,
                outcome.undone !== null && `${outcome.undone} kart arşivden geri alındı`,
                outcome.completed > 0 && `${outcome.completed} kart tamamlandı sayıldı`,
              ]
                .filter(Boolean)
                .join(', ') || 'İşlem yapılmadı'}
              .
            </p>
          )}
          <p className="mt-1 text-sm text-slate-500">
            Arşivlenen kartlar silinmez; aşağıdaki «Geri al» ile bu işlem geri alınır.
          </p>
          <div className="mt-4 flex justify-end gap-3">
            {outcome.archived.length > 0 && (
              <button
                onClick={undo}
                disabled={bulk.isPending}
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:border-slate-900 disabled:opacity-50"
              >
                Arşivlenenleri geri al
              </button>
            )}
            <button onClick={onClose} className="rounded-md bg-slate-900 px-3 py-1.5 text-sm text-on-ink">Kapat</button>
          </div>
        </div>
      )}
    </Modal>
  )
}
