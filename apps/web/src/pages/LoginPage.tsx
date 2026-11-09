import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from '../lib/api'
import { useAuthStore } from '../stores/auth'

interface Tokens {
  access_token: string
  refresh_token: string
}

export default function LoginPage() {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const setTokens = useAuthStore((s) => s.setTokens)
  const navigate = useNavigate()

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      if (mode === 'register') {
        await api('/auth/register', {
          method: 'POST',
          body: JSON.stringify({ email, password, full_name: fullName || null }),
        })
      }
      const tokens = await api<Tokens>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      })
      setTokens(tokens.access_token, tokens.refresh_token)
      navigate('/')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Sunucuya ulaşılamadı')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm space-y-4 rounded-xl bg-surface p-6 shadow-sm ring-1 ring-slate-200"
      >
        <h1 className="text-xl font-semibold">
          {mode === 'login' ? 'Giriş yap' : 'Hesap oluştur'}
        </h1>

        {mode === 'register' && (
          <input
            className="w-full rounded-md border border-slate-300 px-3 py-2"
            placeholder="Ad Soyad"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
          />
        )}
        <input
          className="w-full rounded-md border border-slate-300 px-3 py-2"
          type="email"
          placeholder="E-posta"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <input
          className="w-full rounded-md border border-slate-300 px-3 py-2"
          type="password"
          placeholder="Şifre (en az 8 karakter)"
          required
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        {error && <p className="text-sm text-red-600">{error}</p>}

        <button
          disabled={busy}
          className="w-full rounded-md bg-slate-900 py-2 font-medium text-on-ink disabled:opacity-50"
        >
          {busy ? 'Bekleyin…' : mode === 'login' ? 'Giriş yap' : 'Kaydol'}
        </button>

        <button
          type="button"
          className="w-full text-sm text-slate-600 hover:underline"
          onClick={() => setMode(mode === 'login' ? 'register' : 'login')}
        >
          {mode === 'login' ? 'Hesabın yok mu? Kaydol' : 'Zaten hesabın var mı? Giriş yap'}
        </button>
      </form>
    </div>
  )
}
