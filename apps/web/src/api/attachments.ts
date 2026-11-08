import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, ApiError, BASE, tryRefresh } from '../lib/api'
import { useAuthStore } from '../stores/auth'
import type { Attachment } from '../lib/types'
import { keys } from './boards'

/** Sunucu hata kodlarini kullaniciya Turkce soyler. */
function friendly(status: number, code: string, message: string): string {
  if (status === 413 || code === 'ATTACHMENT_TOO_LARGE') return "Dosya 25 MB'tan büyük"
  if (code === 'ATTACHMENT_TYPE_BLOCKED') return 'Bu dosya türü yüklenemez'
  return message
}

/** multipart yukleme: `api()` JSON basligi koyar, bu yuzden ayri fetch. 401'de bir kez yeniler. */
export async function uploadAttachment(cardId: number, file: File, noteId?: number): Promise<Attachment> {
  const send = () => {
    const form = new FormData()
    form.append('file', file, file.name)
    if (noteId != null) form.append('note_id', String(noteId))
    const token = useAuthStore.getState().accessToken
    return fetch(`${BASE}/cards/${cardId}/attachments`, {
      method: 'POST',
      body: form,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
  }
  let res = await send()
  if (res.status === 401 && (await tryRefresh())) res = await send()
  const body = (await res.json().catch(() => null)) as {
    success?: boolean
    data?: Attachment | null
    error?: { code: string; message: string } | null
    detail?: unknown
  } | null
  if (!res.ok || !body?.success || !body.data) {
    const code = body?.error?.code ?? 'UNKNOWN'
    const msg = body?.error?.message ?? `Yükleme başarısız (${res.status})`
    throw new ApiError(res.status, code, friendly(res.status, code, msg))
  }
  return body.data
}

/** Kart + board sorgularini tazeler (ek sayaci kanban yuzunde). */
function useRefreshCard(cardId: number, boardId?: number) {
  const qc = useQueryClient()
  return () => {
    qc.invalidateQueries({ queryKey: keys.card(cardId) })
    qc.invalidateQueries({ queryKey: keys.activity(cardId) })
    if (boardId != null) qc.invalidateQueries({ queryKey: keys.board(boardId) })
    qc.invalidateQueries({ queryKey: keys.boards })
  }
}

export function useUploadAttachment(cardId: number, boardId?: number) {
  const refresh = useRefreshCard(cardId, boardId)
  return useMutation({
    mutationFn: ({ file, noteId }: { file: File; noteId?: number }) => uploadAttachment(cardId, file, noteId),
    onSuccess: refresh,
  })
}

export function useDeleteAttachment(cardId: number, boardId?: number) {
  const refresh = useRefreshCard(cardId, boardId)
  return useMutation({
    mutationFn: (id: number) => api<void>(`/attachments/${id}`, { method: 'DELETE' }),
    onSuccess: refresh,
  })
}

/**
 * Cok dosyali yukleme + bekleyen adlar + son hata. `upload` basarili olanlari dondurur
 * (editor bunlardan imlece baglanti ekler).
 */
export function useUploads(cardId: number, boardId?: number) {
  const up = useUploadAttachment(cardId, boardId)
  const [pending, setPending] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)

  const upload = async (files: File[], noteId?: number): Promise<Attachment[]> => {
    setError(null)
    const done: Attachment[] = []
    for (const file of files) {
      setPending((p) => [...p, file.name])
      try {
        done.push(await up.mutateAsync({ file, noteId }))
      } catch (e) {
        setError(`${file.name}: ${(e as Error).message}`)
      } finally {
        setPending((p) => {
          const i = p.indexOf(file.name)
          return p.filter((_, j) => j !== i)
        })
      }
    }
    return done
  }
  return { upload, pending, error, clearError: () => setError(null) }
}
