import { useState, type FormEvent, type ReactNode } from 'react'
import { Check, Copy, ExternalLink, Loader2 } from 'lucide-react'
import { useIntegrationMutations, type OAuthClientInfo } from '../api/integrations'

const input = 'rounded-md border border-slate-300 bg-surface px-2 py-1.5 text-sm'

function Link({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 underline">
      {children} <ExternalLink size={12} aria-hidden />
    </a>
  )
}

/** Yönlendirme adresi: tam olarak bu değer sağlayıcıya eklenmeli, o yüzden kopyala düğmesi. */
function CopyField({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      /* pano izni yoksa kullanıcı alanı seçip kopyalar */
    }
  }
  return (
    <span className="mt-1 flex max-w-full flex-wrap items-center gap-2">
      <input
        readOnly
        value={value}
        aria-label={label}
        onFocus={(e) => e.currentTarget.select()}
        className={`${input} w-[26rem] max-w-full font-mono text-[13px]`}
      />
      <button
        type="button"
        onClick={copy}
        className="inline-flex items-center gap-1 rounded-md border border-slate-300 px-2 py-1 text-[13px] hover:bg-slate-100"
      >
        {copied ? <Check size={13} aria-hidden /> : <Copy size={13} aria-hidden />}
        {copied ? 'Kopyalandı' : 'Kopyala'}
      </button>
    </span>
  )
}

function GoogleSteps({ redirectUri }: { redirectUri: string }) {
  return (
    <>
      <li>
        <Link href="https://console.cloud.google.com/projectcreate">Google Cloud’da yeni bir proje oluştur</Link> (ad: örn. “Ajanda”). Üstteki proje seçicide bu projenin seçili olduğundan emin ol.
      </li>
      <li>
        <Link href="https://console.cloud.google.com/apis/library/calendar-json.googleapis.com">Google Calendar API</Link> sayfasında <b>Enable</b>’a bas.
      </li>
      <li>
        <Link href="https://console.cloud.google.com/auth/overview">Google Auth Platform</Link> → <b>Get started</b>: uygulama adı “Ajanda”, destek e-postası kendi adresin, <b>Audience: External</b>, iletişim e-postası → <b>Create</b>.
      </li>
      <li>
        <Link href="https://console.cloud.google.com/auth/audience">Audience</Link> sayfasında <b>Publish app</b>’e bas. <span className="text-slate-500">(Test modunda kalırsa bağlantı 7 günde bir düşer. Yayınlamak için inceleme gerekmez; bağlanırken çıkan “Google bu uygulamayı doğrulamadı” uyarısında <b>Gelişmiş → Ajanda’ya git</b> ile devam et — uygulama senin, veri sadece bu bilgisayara gelir.)</span>
      </li>
      <li>
        <Link href="https://console.cloud.google.com/auth/clients/create">Clients → Create client</Link>: <b>Application type: Web application</b>. <b>Authorized redirect URIs</b> altında <b>Add URI</b> ile tam olarak şunu ekle:
        <CopyField value={redirectUri} label="Google yönlendirme adresi" />
        <b>Create</b>’e bas.
      </li>
      <li>
        Açılan pencereden <b>Client ID</b> ve <b>Client secret</b>’ı aşağı yapıştır. <span className="text-slate-500">(Sır sonradan gösterilmeyebilir; pencereyi kapatmadan kopyala ya da JSON’u indir.)</span>
      </li>
    </>
  )
}

function MicrosoftSteps({ redirectUri }: { redirectUri: string }) {
  return (
    <>
      <li>
        Telefonda <b>Samsung Reminder → Ayarlar → Microsoft To Do ile senkronize et</b>’i aç (hatırlatıcıların To Do’ya gitmesi için).
      </li>
      <li>
        <Link href="https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade">Azure portal → App registrations</Link>’a Microsoft hesabınla gir → <b>New registration</b>. <span className="text-slate-500">(Hesabının bir dizini yoksa portal ücretsiz Azure hesabı açmanı isteyebilir; bu uygulama için ücret çıkmaz.)</span>
      </li>
      <li>
        Ad: “Ajanda”. <b>Supported account types: Personal Microsoft accounts only</b>. <b>Redirect URI</b>: platform <b>Web</b> seç ve tam olarak şunu yapıştır:
        <CopyField value={redirectUri} label="Microsoft yönlendirme adresi" />
        <b>Register</b>’a bas.
      </li>
      <li>
        Açılan <b>Overview</b> sayfasından <b>Application (client) ID</b>’yi kopyala.
      </li>
      <li>
        <b>API permissions → Add a permission → Microsoft Graph → Delegated permissions</b> yolunda <b>Calendars.Read</b>’i işaretleyip ekle (Teams toplantılarını takvime getirmek için; <b>Tasks.ReadWrite</b> ve <b>User.Read</b> zaten varsa dokunma).
      </li>
      <li>
        <b>Certificates &amp; secrets → Client secrets → New client secret</b> (süre: örn. 24 ay) → <b>Add</b>. Tablodaki <b>Value</b> sütununu hemen kopyala — <b>Secret ID</b> değil; sayfadan çıkınca bir daha görünmez.
      </li>
      <li>
        İkisini aşağı yapıştır. <span className="text-slate-500">(Sırrın süresi dolunca Azure’da yenisini oluşturup buradan “Kimlik bilgilerini değiştir” ile gir.)</span>
      </li>
    </>
  )
}

const LABELS = {
  google: { name: 'Google', id: 'Client ID (….apps.googleusercontent.com)', secret: 'Client secret' },
  microsoft: { name: 'Microsoft', id: 'Application (client) ID', secret: 'Client secret “Value”' },
}

/**
 * Google/Microsoft uygulama kimliği kurulum sihirbazı: adım adım ne yapılacağı,
 * kopyalanacak yönlendirme adresi, kimlik/sır girişi → "Kaydet ve bağlan".
 */
export default function OAuthSetup({ info, onCancel }: { info: OAuthClientInfo; onCancel?: () => void }) {
  const { saveOAuthClient, connectOAuth } = useIntegrationMutations()
  const [clientId, setClientId] = useState('')
  const [secret, setSecret] = useState('')
  const labels = LABELS[info.provider]
  const busy = saveOAuthClient.isPending || connectOAuth.isPending

  const submit = (e: FormEvent) => {
    e.preventDefault()
    saveOAuthClient.mutate(
      { provider: info.provider, client_id: clientId.trim(), client_secret: secret.trim() },
      {
        onSuccess: () => {
          setSecret('')
          connectOAuth.mutate(info.provider)
        },
      },
    )
  }

  return (
    <form onSubmit={submit} className="space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-4 mb-4">
      <p className="text-[15px] font-semibold">{labels.name} bağlantısını kur (bir kerelik, ~5 dk)</p>
      <p className="max-w-prose text-[14px] text-slate-600">
        Ajanda senin bilgisayarında çalıştığı için {labels.name}’a onu kendi “uygulama kimliğinle” tanıtman gerekiyor.
        Adımları sırayla yap; bağlantılar yeni sekmede açılır.
      </p>
      <ol className="max-w-prose list-decimal space-y-2 pl-5 text-[14px] text-slate-700">
        {info.provider === 'google' ? <GoogleSteps redirectUri={info.redirect_uri} /> : <MicrosoftSteps redirectUri={info.redirect_uri} />}
      </ol>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-[13px] text-slate-600">
          {labels.id}
          <input className={`${input} w-80 max-w-full`} autoComplete="off" spellCheck={false} value={clientId} onChange={(e) => setClientId(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1 text-[13px] text-slate-600">
          {labels.secret}
          <input className={`${input} w-72 max-w-full`} type="password" autoComplete="off" value={secret} onChange={(e) => setSecret(e.target.value)} />
        </label>
        <button
          disabled={busy || !clientId.trim() || !secret.trim()}
          className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-4 py-1.5 text-[15px] text-on-ink hover:bg-slate-700 disabled:opacity-40"
        >
          {busy && <Loader2 size={14} className="animate-spin" aria-hidden />} Kaydet ve bağlan
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel} className="px-2 py-1.5 text-[14px] text-slate-600 hover:underline">
            Vazgeç
          </button>
        )}
      </div>
      <p className="text-[13px] text-slate-500">Sır bu bilgisayarda şifreli saklanır ve bir daha gösterilmez.</p>
      {saveOAuthClient.error && <p className="text-[14px] text-red-700">{saveOAuthClient.error.message}</p>}
      {connectOAuth.error && <p className="text-[14px] text-red-700">{connectOAuth.error.message}</p>}
    </form>
  )
}
