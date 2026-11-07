// Backend OpenAPI semasindan uretilen tipler (npm run gen:api).
//
// Not: openapi-typescript varsayilan degeri olan alanlari yanitlarda opsiyonel,
// isteklerde zorunlu yapiyor. Gercekte tersi gecerli (sunucu yanitta her zaman
// doldurur, istekte gondermek opsiyonel) -> asagidaki iki yardimci bunu duzeltir.
import type { components } from './api-schema'

type S = components['schemas']

/** Yanit: sunucu tum alanlari doldurur. */
type Res<T> = { [K in keyof T]-?: Exclude<T[K], undefined> }
/** Istek: varsayilani olan alanlar opsiyonel. */
type Req<T, K extends keyof T> = Omit<T, K> & Partial<Pick<T, K>>

export type Board = Res<S['BoardResponse']>
export type BoardWithCounts = Res<S['BoardWithCounts']>
export type BoardList = Res<S['ListResponse']>
export type Label = Res<S['LabelResponse']>
export type CardSummary = Res<S['CardSummary']>
export type Note = Res<S['NoteResponse']>
export type ChecklistItem = Res<S['ChecklistItemResponse']>
export type Activity = Res<S['ActivityResponse']>
export type UserSettings = Res<S['UserSettingsResponse']>

export type CardDetail = Omit<Res<S['CardDetail']>, 'notes' | 'checklist'> & {
  notes: Note[]
  checklist: ChecklistItem[]
}
export type BoardDetail = {
  board: Board
  lists: BoardList[]
  cards: CardSummary[]
  labels: Label[]
}

export type BoardCreate = Req<S['BoardCreate'], 'color' | 'privacy'>
export type BoardUpdate = S['BoardUpdate']
export type CardCreate = Req<S['CardCreate'], 'priority' | 'label_ids'>
export type CardUpdate = S['CardUpdate']
export type UserSettingsUpdate = S['UserSettingsUpdate']
export type TaskPriority = S['TaskPriority']
export type TaskStatus = S['TaskStatus']
