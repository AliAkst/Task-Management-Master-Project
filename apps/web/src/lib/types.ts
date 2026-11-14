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
export type Attachment = Res<S['AttachmentResponse']>
export type ChecklistItem = Res<S['ChecklistItemResponse']>
export type Activity = Res<S['ActivityResponse']>
export type UserSettings = Res<S['UserSettingsResponse']>
export type WhenMatch = S['WhenMatchOut'] // Res degil: TitleParse.match ic ice Res'lenmez, due_date/estimated_minutes opsiyonel kalir
export type TitleParse = Res<S['TitleParseResponse']>

export type CardRef = Res<S['CardRef']>
export type CardDetail = Omit<
  Res<S['CardDetail']>,
  'notes' | 'attachments' | 'checklist' | 'subtasks' | 'depends_on' | 'dependents' | 'parent'
> & {
  notes: Note[]
  attachments: Attachment[]
  checklist: ChecklistItem[]
  subtasks: CardSummary[]
  depends_on: CardRef[]
  dependents: CardRef[]
  parent: CardRef | null
}
export type GraphEdge = Res<S['GraphEdge']>
export type BoardGraph = { nodes: CardSummary[]; edges: GraphEdge[] }
export type CardSplit = Req<S['CardSplit'], 'chain'>
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

// ---------------- Takvim (Faz 2) ----------------
export type CalendarItem = Res<S['CalendarItem']>
export type CalendarEvent = Res<S['EventResponse']>
export type EventCreate = Req<S['EventCreate'], 'all_day' | 'add_to_plan'>
export type EventUpdate = S['EventUpdate']

// ---------------- Zaman takibi (Faz 3a) ----------------
export type TimeSession = Res<S['SessionResponse']>
export type SessionManualCreate = S['SessionManualCreate']

// ---------------- Planlama & istatistik (Faz 3b) ----------------
export type DayPlan = Omit<Res<S['DayPlanResponse']>, 'items'> & { items: DayPlanItem[] }
export type DayPlanItem = Res<S['DayPlanItemResponse']>
export type PlanSuggestion = Res<S['PlanSuggestion']>
export type PlanItemInput = S['PlanItemInput']
export type DayPlanItemPatch = S['DayPlanItemPatch']
export type ItemToCard = S['ItemToCard']
export type ItemMove = S['ItemMove']
export type DayReview = S['DayReview']
export type ItemOutcome = S['ItemOutcome']
export type AnalyticsSummary = Res<S['AnalyticsSummary']>
