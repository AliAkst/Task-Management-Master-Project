import { useEffect, useState, type FormEvent } from 'react'
import { Check, ExternalLink, Loader2, RefreshCw, Unplug } from 'lucide-react'
import {
  useIntegrationMutations,
  useGoogleCalendars,
  useIntegrations,
  useMicrosoftLists,
  useMicrosoftStatus,
  useTrelloBoards,
  type IntegrationAccount,
  type SyncSummary,
  type TrelloImportResult,
} from '../api/integrations'
import { useBoards } from '../api/boards'
import { formatDateTime } from '../lib/format'
import { Row } from './Page'

const input = 'rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm'

/** Sonuc ozeti: "3 liste, 12 kart, 5 madde, 2 not (4 kart zaten vardı)". */
function summary(r: TrelloImportResult) {
  const parts = [
    r.lists && `${r.lists} liste`,
    r.cards && `${r.cards} kart`,
    r.checklist_items && `${r.checklist_items} madde`,
    r.notes && `${r.notes} not`,
  ].filter(Boolean)
  const added = parts.length ? parts.join(', ') : 'yeni bir şey yok'
  return r.skipped_cards ? `${added} (${r.skipped_cards} kart zaten vardı)` : added
}

function TrelloConnectForm() {
  const { connectTrello } = useIntegrationMutations()
  const [apiKey, setApiKey] = useState('')
  const [token, setToken] = useState('')
  const key = apiKey.trim()
  const tokenUrl = `https://trello.com/1/authorize?expiration=never&scope=read&response_type=token&key=${encodeURIComponent(key)}&name=Ajanda`

  const submit = (e: FormEvent) => {
    e.preventDefault()
    connectTrello.mutate(
      { api_key: key, token: token.trim() },
      {
        onSuccess: () => {
          setApiKey('')
          setToken('')
        },
      },
    )
  }

  return (
    <form onSubmit={submit} className="space-y-3 pb-4">
      <ol className="max-w-prose list-decimal space-y-1 pl-5 text-[14px] text-slate-600">
        <li>
          <a href="https://trello.com/power-ups/admin" target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 underline">
            Trello Power-Up yöneticisinde <ExternalLink size={12} aria-hidden />
          </a>{' '}
          bir Power-Up oluştur ve <b>API anahtarını</b> kopyala.
        </li>
        <li>
          Anahtarı aşağı yapıştırınca çıkan <b>“Token al”</b> bağlantısından izin ver (salt okunur) ve token’ı yapıştır.
        </li>
      </ol>
      <div className="flex flex-wrap items-center gap-2">
        <input className={`${input} w-64`} placeholder="API anahtarı" aria-label="Trello API anahtarı" autoComplete="off" value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
        <input className={`${input} w-72`} type="password" placeholder="Token" aria-label="Trello token" autoComplete="off" value={token} onChange={(e) => setToken(e.target.value)} />
        {key.length >= 8 && (
          <a href={tokenUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[14px] underline">
            Token al <ExternalLink size={12} aria-hidden />
          </a>
        )}
        <button
          disabled={connectTrello.isPending || key.length < 8 || token.trim().length < 8}
          className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-4 py-1.5 text-[15px] text-white hover:bg-slate-700 disabled:opacity-40"
        >
          {connectTrello.isPending && <Loader2 size={14} className="animate-spin" aria-hidden />} Bağlan
        </button>
      </div>
      {connectTrello.error && <p className="text-[14px] text-red-700">{connectTrello.error.message}</p>}
    </form>
  )
}

function TrelloBoards() {
  const boards = useTrelloBoards(true)
  const { importTrello } = useIntegrationMutations()
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  return (
    <div className="space-y-3 pb-4">
      {boards.isLoading && <p className="text-[14px] text-slate-500">Board’lar getiriliyor…</p>}
      {boards.error && <p className="text-[14px] text-red-700">{boards.error.message}</p>}
      {boards.data?.length === 0 && <p className="text-[14px] text-slate-600">Trello’da açık board bulunamadı.</p>}
      {boards.data && boards.data.length > 0 && (
        <fieldset>
          <legend className="mb-1 text-[14px] text-slate-600">
            İçe aktarılacak board’ları seç. Tekrar içe aktarmak var olanlara dokunmaz, sadece yenileri ekler.
          </legend>
          <ul className="divide-y divide-slate-200 border-y border-slate-200">
            {boards.data.map((b) => (
              <li key={b.id}>
                <label className="flex cursor-pointer items-center gap-3 py-2">
                  <input type="checkbox" checked={selected.has(b.id)} onChange={() => toggle(b.id)} />
                  <span className="min-w-0 flex-1 truncate">{b.name}</span>
                  {b.already_imported && (
                    <span className="inline-flex items-center gap-1 text-[13px] text-slate-500">
                      <Check size={12} aria-hidden /> içe aktarıldı
                    </span>
                  )}
                </label>
              </li>
            ))}
          </ul>
        </fieldset>
      )}
      <button
        disabled={selected.size === 0 || importTrello.isPending}
        onClick={() => importTrello.mutate([...selected], { onSuccess: () => setSelected(new Set()) })}
        className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-4 py-1.5 text-[15px] text-white hover:bg-slate-700 disabled:opacity-40"
      >
        {importTrello.isPending && <Loader2 size={14} className="animate-spin" aria-hidden />}
        İçe aktar{selected.size > 0 ? ` (${selected.size})` : ''}
      </button>
      {importTrello.error && <p className="text-[14px] text-red-700">{importTrello.error.message}</p>}
      {importTrello.data && (
        <ul className="space-y-1 text-[14px]" aria-live="polite">
          {importTrello.data.map((r) => (
            <li key={r.trello_board_id} className={r.error ? 'text-red-700' : 'text-slate-700'}>
              <b>{r.name}</b>: {r.error ?? summary(r)}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function TrelloRow({ account }: { account: IntegrationAccount | undefined }) {
  const { disconnect } = useIntegrationMutations()
  return (
    <div>
      <Row
        title="Trello"
        hint={
          account
            ? `Bağlı: ${account.account_label ?? 'hesap'} · anahtar ${account.masked_credentials.api_key ?? '…'}`
            : 'Board’larını, kartlarını, checklist ve yorumlarını tek seferlik içe aktar.'
        }
      >
        {account && (
          <button
            onClick={() => {
              if (confirm('Trello bağlantısı kaldırılsın mı? İçe aktarılan kartlar silinmez.')) disconnect.mutate('trello')
            }}
            className="inline-flex items-center gap-1.5 text-sm text-red-700 hover:underline"
          >
            <Unplug size={14} aria-hidden /> Bağlantıyı kaldır
          </button>
        )}
      </Row>
      {disconnect.error && <p className="pb-2 text-[14px] text-red-700">{disconnect.error.message}</p>}
      {account ? <TrelloBoards /> : <TrelloConnectForm />}
    </div>
  )
}

function syncText(r: SyncSummary) {
  const parts = [r.created && `${r.created} yeni`, r.updated && `${r.updated} güncellendi`, r.removed && `${r.removed} silindi`].filter(Boolean)
  return parts.length ? parts.join(', ') : 'değişiklik yok'
}

function GoogleCalendars({ account }: { account: IntegrationAccount }) {
  const calendars = useGoogleCalendars(account.status === 'active')
  const boards = useBoards()
  const { saveGoogleSettings, syncNow } = useIntegrationMutations()
  const [picked, setPicked] = useState<Set<string> | null>(null)
  const [boardId, setBoardId] = useState<number | null | undefined>(undefined)

  const savedIds = new Set((account.settings?.calendar_ids as string[] | undefined) ?? [])
  const selected = picked ?? savedIds
  const savedBoard = (account.settings?.board_id as number | null | undefined) ?? null
  const board = boardId === undefined ? savedBoard : boardId
  const dirty = picked !== null || boardId !== undefined

  const toggle = (id: string) => {
    const next = new Set(selected)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setPicked(next)
  }
  const save = () =>
    saveGoogleSettings.mutate(
      { calendar_ids: [...selected], board_id: board },
      {
        onSuccess: () => {
          setPicked(null)
          setBoardId(undefined)
          if (selected.size > 0) syncNow.mutate('google')
        },
      },
    )

  return (
    <div className="space-y-3 pb-4">
      {calendars.isLoading && <p className="text-[14px] text-slate-500">Takvimler getiriliyor…</p>}
      {calendars.error && <p className="text-[14px] text-red-700">{calendars.error.message}</p>}
      {calendars.data && (
        <fieldset>
          <legend className="mb-1 text-[14px] text-slate-600">
            Senkronlanacak takvimleri seç. Etkinlikler burada salt okunur görünür; seçimi kaldırırsan o takvimin etkinlikleri silinir.
          </legend>
          <ul className="divide-y divide-slate-200 border-y border-slate-200">
            {calendars.data.map((c) => (
              <li key={c.id}>
                <label className="flex cursor-pointer items-center gap-3 py-2">
                  <input type="checkbox" checked={selected.has(c.id)} onChange={() => toggle(c.id)} />
                  <span aria-hidden className="size-2.5 rounded-full" style={{ background: c.color ?? '#64748b' }} />
                  <span className="min-w-0 flex-1 truncate">{c.summary}</span>
                  {c.primary && <span className="text-[13px] text-slate-500">ana takvim</span>}
                </label>
              </li>
            ))}
          </ul>
        </fieldset>
      )}
      <label className="flex flex-wrap items-center gap-2 text-[14px] text-slate-600">
        Etkinliklerin rengi ve board’u
        <select className={input} value={board ?? ''} onChange={(e) => setBoardId(e.target.value ? Number(e.target.value) : null)}>
          <option value="">— Board’suz —</option>
          {(boards.data ?? []).map((b) => (
            <option key={b.id} value={b.id}>{b.name}</option>
          ))}
        </select>
      </label>
      <div className="flex flex-wrap items-center gap-3">
        <button
          disabled={!dirty || saveGoogleSettings.isPending}
          onClick={save}
          className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-4 py-1.5 text-[15px] text-white hover:bg-slate-700 disabled:opacity-40"
        >
          {saveGoogleSettings.isPending && <Loader2 size={14} className="animate-spin" aria-hidden />} Kaydet
        </button>
        <button
          disabled={savedIds.size === 0 || syncNow.isPending}
          onClick={() => syncNow.mutate('google')}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 px-4 py-1.5 text-[15px] hover:bg-slate-100 disabled:opacity-40"
        >
          <RefreshCw size={14} className={syncNow.isPending ? 'animate-spin' : ''} aria-hidden /> Şimdi senkronla
        </button>
      </div>
      {saveGoogleSettings.error && <p className="text-[14px] text-red-700">{saveGoogleSettings.error.message}</p>}
      {syncNow.error && <p className="text-[14px] text-red-700">{syncNow.error.message}</p>}
      {syncNow.data && (
        <p className={`text-[14px] ${syncNow.data.errors.length ? 'text-red-700' : 'text-slate-700'}`} aria-live="polite">
          {syncText(syncNow.data)}
          {syncNow.data.errors.length > 0 && ` · hata: ${syncNow.data.errors.join('; ')}`}
        </p>
      )}
    </div>
  )
}

function GoogleRow({ account }: { account: IntegrationAccount | undefined }) {
  const { connectOAuth, disconnect } = useIntegrationMutations()
  const reconnect = account?.status === 'error'
  const hint = !account
    ? 'Takvim etkinliklerini (salt okunur) buraya getir; 15 dakikada bir kendiliğinden güncellenir.'
    : [
        `Bağlı: ${account.account_label ?? 'hesap'}`,
        account.last_synced_at ? `son senkron ${formatDateTime(account.last_synced_at)}` : 'henüz senkronlanmadı',
      ].join(' · ')
  return (
    <div>
      <Row title="Google Takvim" hint={hint}>
        <div className="flex items-center gap-4">
          {(!account || reconnect) && (
            <button
              disabled={connectOAuth.isPending}
              onClick={() => connectOAuth.mutate('google')}
              className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-4 py-1.5 text-[15px] text-white hover:bg-slate-700 disabled:opacity-40"
            >
              {connectOAuth.isPending && <Loader2 size={14} className="animate-spin" aria-hidden />}
              {reconnect ? 'Yeniden bağlan' : 'Google ile bağlan'}
            </button>
          )}
          {account && (
            <button
              onClick={() => {
                if (confirm('Google Takvim bağlantısı kesilsin mi? Oradan gelen etkinlikler buradan silinir (Google’daki etkinliklere dokunulmaz).')) disconnect.mutate('google')
              }}
              className="inline-flex items-center gap-1.5 text-sm text-red-700 hover:underline"
            >
              <Unplug size={14} aria-hidden /> Bağlantıyı kes
            </button>
          )}
        </div>
      </Row>
      {connectOAuth.error && <p className="pb-2 text-[14px] text-red-700">{connectOAuth.error.message}</p>}
      {disconnect.error && <p className="pb-2 text-[14px] text-red-700">{disconnect.error.message}</p>}
      {account?.last_error && <p className="pb-2 text-[14px] text-red-700">{account.last_error}</p>}
      {account && !reconnect && <GoogleCalendars account={account} />}
    </div>
  )
}

function MicrosoftLists({ account }: { account: IntegrationAccount }) {
  const lists = useMicrosoftLists(account.status === 'active')
  const status = useMicrosoftStatus(account.status === 'active')
  const { saveMicrosoftSettings, syncNow } = useIntegrationMutations()
  const [picked, setPicked] = useState<Set<string> | null>(null)

  const all = lists.data ?? []
  const selected = picked ?? new Set(all.filter((l) => l.selected).map((l) => l.id))
  const toggle = (id: string) => {
    const next = new Set(selected)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setPicked(next)
  }
  // Hepsi seçiliyse null (sonradan eklenen listeler de dahil olsun)
  const save = () =>
    saveMicrosoftSettings.mutate(selected.size === all.length ? null : [...selected], {
      onSuccess: () => {
        setPicked(null)
        if (selected.size > 0) syncNow.mutate('microsoft')
      },
    })

  return (
    <div className="space-y-3 pb-4">
      {lists.isLoading && <p className="text-[14px] text-slate-500">Listeler getiriliyor…</p>}
      {lists.error && <p className="text-[14px] text-red-700">{lists.error.message}</p>}
      {all.length > 0 && (
        <fieldset>
          <legend className="mb-1 max-w-prose text-[14px] text-slate-600">
            Senkronlanacak listeleri seç. Yeni görevler “Gelen Kutusu”na düşer; burada tamamladığın kart To Do’da da tamamlanır. Bir listeyi çıkarırsan kartlar kalır, sadece To Do ile bağı kopar.
          </legend>
          <ul className="divide-y divide-slate-200 border-y border-slate-200">
            {all.map((l) => (
              <li key={l.id}>
                <label className="flex cursor-pointer items-center gap-3 py-2">
                  <input type="checkbox" checked={selected.has(l.id)} onChange={() => toggle(l.id)} />
                  <span className="min-w-0 flex-1 truncate">{l.name}</span>
                </label>
              </li>
            ))}
          </ul>
        </fieldset>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <button
          disabled={picked === null || selected.size === 0 || saveMicrosoftSettings.isPending}
          onClick={save}
          className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-4 py-1.5 text-[15px] text-white hover:bg-slate-700 disabled:opacity-40"
        >
          {saveMicrosoftSettings.isPending && <Loader2 size={14} className="animate-spin" aria-hidden />} Kaydet
        </button>
        <button
          disabled={syncNow.isPending}
          onClick={() => syncNow.mutate('microsoft')}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 px-4 py-1.5 text-[15px] hover:bg-slate-100 disabled:opacity-40"
        >
          <RefreshCw size={14} className={syncNow.isPending ? 'animate-spin' : ''} aria-hidden /> Şimdi senkronla
        </button>
        {status.data && status.data.pending_push > 0 && (
          <span className={`text-[14px] ${status.data.failed_push ? 'text-red-700' : 'text-slate-600'}`}>
            {status.data.pending_push} tamamlama To Do’ya yazılmayı bekliyor
            {status.data.failed_push > 0 && ` (${status.data.failed_push} tanesi hata aldı, sonraki turda tekrar denenecek)`}
          </span>
        )}
      </div>
      {saveMicrosoftSettings.error && <p className="text-[14px] text-red-700">{saveMicrosoftSettings.error.message}</p>}
      {syncNow.error && <p className="text-[14px] text-red-700">{syncNow.error.message}</p>}
      {syncNow.data && (
        <p className={`text-[14px] ${syncNow.data.errors.length ? 'text-red-700' : 'text-slate-700'}`} aria-live="polite">
          {syncText(syncNow.data)}
          {syncNow.data.errors.length > 0 && ` · hata: ${syncNow.data.errors.join('; ')}`}
        </p>
      )}
    </div>
  )
}

function MicrosoftRow({ account }: { account: IntegrationAccount | undefined }) {
  const { connectOAuth, disconnect } = useIntegrationMutations()
  const reconnect = account?.status === 'error'
  const hint = !account
    ? 'Samsung Reminder / To Do görevlerini Gelen Kutusu’na getir; kartı bitirince To Do’da da biter. 15 dakikada bir güncellenir.'
    : [
        `Bağlı: ${account.account_label ?? 'hesap'}`,
        account.last_synced_at ? `son senkron ${formatDateTime(account.last_synced_at)}` : 'henüz senkronlanmadı',
      ].join(' · ')
  return (
    <div>
      <Row title="Microsoft To Do" hint={hint}>
        <div className="flex items-center gap-4">
          {(!account || reconnect) && (
            <button
              disabled={connectOAuth.isPending}
              onClick={() => connectOAuth.mutate('microsoft')}
              className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-4 py-1.5 text-[15px] text-white hover:bg-slate-700 disabled:opacity-40"
            >
              {connectOAuth.isPending && <Loader2 size={14} className="animate-spin" aria-hidden />}
              {reconnect ? 'Yeniden bağlan' : 'Microsoft ile bağlan'}
            </button>
          )}
          {account && (
            <button
              onClick={() => {
                if (confirm('Microsoft To Do bağlantısı kesilsin mi? Gelen Kutusu’ndaki kartlar silinmez, To Do’ya dokunulmaz.')) disconnect.mutate('microsoft')
              }}
              className="inline-flex items-center gap-1.5 text-sm text-red-700 hover:underline"
            >
              <Unplug size={14} aria-hidden /> Bağlantıyı kes
            </button>
          )}
        </div>
      </Row>
      {connectOAuth.error && <p className="pb-2 text-[14px] text-red-700">{connectOAuth.error.message}</p>}
      {disconnect.error && <p className="pb-2 text-[14px] text-red-700">{disconnect.error.message}</p>}
      {account?.last_error && <p className="pb-2 text-[14px] text-red-700">{account.last_error}</p>}
      {account && !reconnect && <MicrosoftLists account={account} />}
    </div>
  )
}

/** OAuth dönüşü: ?connected=google ya da ?connect_error=google&message=… */
function useOAuthReturn() {
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null)
  useEffect(() => {
    const q = new URLSearchParams(window.location.search)
    const connected = q.get('connected')
    const failed = q.get('connect_error')
    if (!connected && !failed) return
    setNotice(
      connected
        ? {
            ok: true,
            text:
              connected === 'microsoft'
                ? 'Microsoft To Do bağlandı. Senkronlanacak listeleri seçip kaydet.'
                : 'Google Takvim bağlandı. Senkronlanacak takvimleri seç.',
          }
        : { ok: false, text: `Bağlantı kurulamadı: ${q.get('message') ?? 'bilinmeyen hata'}` },
    )
    window.history.replaceState(null, '', window.location.pathname + window.location.hash)
  }, [])
  return notice
}

export default function IntegrationsSettings() {
  const accounts = useIntegrations()
  const trello = accounts.data?.find((a) => a.provider === 'trello')
  const google = accounts.data?.find((a) => a.provider === 'google')
  const microsoft = accounts.data?.find((a) => a.provider === 'microsoft')
  const notice = useOAuthReturn()
  return (
    <section id="baglantilar" className="scroll-mt-6">
      <h2 className="text-[22px]">Bağlantılar</h2>
      <p className="mt-1 mb-2 max-w-prose text-[15px] text-slate-600">
        Başka yerlerdeki işlerini buraya al. İçe aktarılanlar “Gelen Kutusu” ya da kendi board’larında görünür.
      </p>
      {notice && (
        <p role="status" className={`mb-2 text-[14px] ${notice.ok ? 'text-green-700' : 'text-red-700'}`}>
          {notice.text}
        </p>
      )}
      {accounts.error && <p className="text-[14px] text-red-700">{accounts.error.message}</p>}
      <div className="divide-y divide-slate-200 border-y border-slate-200">
        {accounts.data && <GoogleRow account={google} />}
        {accounts.data && <MicrosoftRow account={microsoft} />}
        {accounts.data && <TrelloRow account={trello} />}
      </div>
    </section>
  )
}
