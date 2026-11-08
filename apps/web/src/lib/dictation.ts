/**
 * Dikte metnini imlec konumuna eklemek icin hazirlar: gerekirse onune bosluk,
 * cumle basinda buyuk harf (tr-TR: i -> İ).
 */
export function prepareDictated(before: string, text: string): string {
  let t = text.trim()
  if (!t) return ''
  const prev = before.trimEnd()
  const atSentenceStart = prev === '' || /[.!?]$/.test(prev) || /\n\s*$/.test(before)
  if (atSentenceStart) t = t.charAt(0).toLocaleUpperCase('tr-TR') + t.slice(1)
  const needSpace = before.length > 0 && !/\s$/.test(before)
  return (needSpace ? ' ' : '') + t
}

/** Ctrl+M dikte kisayolu mu? */
export function isDictationKey(e: { key: string; ctrlKey: boolean; altKey: boolean; shiftKey: boolean; metaKey: boolean }): boolean {
  return e.ctrlKey && !e.altKey && !e.shiftKey && !e.metaKey && e.key.toLowerCase() === 'm'
}

/** Bir input/textarea'nin imlec konumuna dikte metni ekler; yeni deger ve imlec dondurur. */
export function insertDictated(value: string, selStart: number | null, selEnd: number | null, text: string): { value: string; caret: number } {
  const s = selStart ?? value.length
  const e = selEnd ?? value.length
  const piece = prepareDictated(value.slice(0, s), text)
  return { value: value.slice(0, s) + piece + value.slice(e), caret: s + piece.length }
}
