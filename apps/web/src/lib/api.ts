import { useAuthStore } from '../stores/auth'

/** Backend'in tum yanitlari bu sarmalda gelir (app/models/common.py -> ApiResponse[T]). */
interface ApiEnvelope<T> {
  success: boolean
  data: T | null
  error: { code: string; message: string } | null
}

export class ApiError extends Error {
  status: number
  code: string
  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

export const BASE = '/api/v1'

/** FastAPI'nin 422 dogrulama hatasi formati: {detail: [{loc, msg}]} */
interface ValidationDetail {
  loc: (string | number)[]
  msg: string
}

function formatDetail(detail: ValidationDetail[] | string | undefined): string | null {
  if (!detail) return null
  if (typeof detail === 'string') return detail
  return detail.map((d) => `${d.loc[d.loc.length - 1]}: ${d.msg}`).join(' · ')
}

export async function tryRefresh(): Promise<boolean> {
  const { refreshToken, setTokens, logout } = useAuthStore.getState()
  if (!refreshToken) return false
  const res = await fetch(`${BASE}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  })
  if (!res.ok) {
    logout()
    return false
  }
  const body = (await res.json()) as ApiEnvelope<{ access_token: string; refresh_token: string }>
  if (!body.data) return false
  setTokens(body.data.access_token, body.data.refresh_token)
  return true
}

/** JSON istek atar, ApiResponse sarmalini acar; 401'de bir kez token yenilemeyi dener. */
export async function api<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const token = useAuthStore.getState().accessToken
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  })

  if (res.status === 401 && retry && (await tryRefresh())) {
    return api<T>(path, init, false)
  }
  if (res.status === 204) return undefined as T

  const body = (await res.json().catch(() => null)) as
    | (ApiEnvelope<T> & { detail?: ValidationDetail[] | string })
    | null
  if (!res.ok || !body?.success) {
    throw new ApiError(
      res.status,
      body?.error?.code ?? (res.status === 422 ? 'VALIDATION_ERROR' : 'UNKNOWN'),
      body?.error?.message ?? formatDetail(body?.detail) ?? `İstek başarısız (${res.status})`,
    )
  }
  return body.data as T
}
