import type { QueryClient } from '@tanstack/react-query'
import { parseTitleNow, type NewCardInput } from '../api/boards'
import type { WhenMatch } from './types'

/**
 * Baslikta algilanan zaman ifadesini kart verisine cevirir (00-genel K7/K13).
 * Kabul: eslesme var, sonucu mevcut metne ait (`ready`) ve kullanici reddetmemis.
 * Aksi halde yalniz kirpilmis baslik gider.
 */
export function applyWhen(
  title: string,
  match: WhenMatch | null,
  ready: boolean,
  dismissed: string | null,
): NewCardInput {
  if (!match || !ready || match.phrase === dismissed) return { title: title.trim() }
  const data: NewCardInput = { title: match.clean_title }
  if (match.due_date) data.due_date = match.due_date
  if (match.estimated_minutes) data.estimated_minutes = match.estimated_minutes
  return data
}

/**
 * Gonderimde sonuc hazirsa onu kullanir; degilse bir kez ayristirmayi bekler (400 ms, 11b / L2).
 * Zaman asimi/hata -> yalniz baslik. `synced` = senkron yol (Takvime de koy gonderilmez).
 */
export async function resolveWhen(
  title: string,
  current: { match: WhenMatch | null; ready: boolean },
  dismissed: string | null,
  qc: QueryClient,
): Promise<{ data: NewCardInput; synced: boolean }> {
  if (current.ready) return { data: applyWhen(title, current.match, true, dismissed), synced: false }
  const m = await parseTitleNow(qc, title)
  if (m === undefined) return { data: { title: title.trim() }, synced: true }
  return { data: applyWhen(title, m, true, dismissed), synced: true }
}
