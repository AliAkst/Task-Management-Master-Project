import type { NewCardInput } from '../api/boards'
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
