import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import type {
  Activity,
  Board,
  BoardCreate,
  BoardDetail,
  BoardList,
  BoardUpdate,
  BoardGraph,
  BoardWithCounts,
  CardCreate,
  CardDetail,
  CardSplit,
  CardUpdate,
  ChecklistItem,
  Label,
  Note,
} from '../lib/types'

export const keys = {
  boards: ['boards'] as const,
  board: (id: number) => ['board', id] as const,
  graph: (id: number) => ['board', id, 'graph'] as const,
  card: (id: number) => ['card', id] as const,
  activity: (id: number) => ['card', id, 'activity'] as const,
}

const json = (body: unknown) => ({ body: JSON.stringify(body) })

// ---------------- sorgular ----------------
export function useBoards() {
  return useQuery({ queryKey: keys.boards, queryFn: () => api<BoardWithCounts[]>('/boards') })
}

export function useBoard(id: number) {
  return useQuery({ queryKey: keys.board(id), queryFn: () => api<BoardDetail>(`/boards/${id}`) })
}

export function useBoardGraph(id: number, enabled = true) {
  return useQuery({
    queryKey: keys.graph(id),
    queryFn: () => api<BoardGraph>(`/boards/${id}/graph`),
    enabled,
  })
}

export function useCard(id: number | null) {
  return useQuery({
    queryKey: keys.card(id ?? 0),
    queryFn: () => api<CardDetail>(`/cards/${id}`),
    enabled: id !== null,
  })
}

export function useCardActivity(id: number | null) {
  return useQuery({
    queryKey: keys.activity(id ?? 0),
    queryFn: () => api<Activity[]>(`/cards/${id}/activity`),
    enabled: id !== null,
  })
}

// ---------------- board ----------------
export function useCreateBoard() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: BoardCreate) => api<Board>('/boards', { method: 'POST', ...json(data) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.boards }),
  })
}

export function useUpdateBoard(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: BoardUpdate) =>
      api<Board>(`/boards/${id}`, { method: 'PATCH', ...json(data) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.boards })
      qc.invalidateQueries({ queryKey: keys.board(id) })
    },
  })
}

export function useDeleteBoard() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api<void>(`/boards/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.boards }),
  })
}

// ---------------- board icerigi (liste, etiket, kart tasima) ----------------
/** Board ekraninda kullanilan, islem sonunda board'u yenileyen mutation'lar. */
export function useBoardMutations(boardId: number) {
  const qc = useQueryClient()
  const refresh = () => {
    qc.invalidateQueries({ queryKey: keys.board(boardId) })
    qc.invalidateQueries({ queryKey: keys.boards })
  }

  return {
    createList: useMutation({
      mutationFn: (name: string) =>
        api<BoardList>(`/boards/${boardId}/lists`, { method: 'POST', ...json({ name }) }),
      onSuccess: refresh,
    }),
    updateList: useMutation({
      mutationFn: ({ id, ...data }: { id: number; name?: string; is_done_list?: boolean }) =>
        api<BoardList>(`/lists/${id}`, { method: 'PATCH', ...json(data) }),
      onSuccess: refresh,
    }),
    deleteList: useMutation({
      mutationFn: (id: number) => api<void>(`/lists/${id}`, { method: 'DELETE' }),
      onSuccess: refresh,
    }),
    moveList: useMutation({
      mutationFn: ({ id, index }: { id: number; index: number }) =>
        api<BoardList>(`/lists/${id}/move`, { method: 'POST', ...json({ index }) }),
      onSettled: refresh,
    }),
    createCard: useMutation({
      mutationFn: (data: CardCreate) =>
        api<CardDetail>('/cards', { method: 'POST', ...json(data) }),
      onSuccess: refresh,
    }),
    moveCard: useMutation({
      mutationFn: ({ id, list_id, index }: { id: number; list_id: number; index: number }) =>
        api<CardDetail>(`/cards/${id}/move`, { method: 'POST', ...json({ list_id, index }) }),
      onSettled: refresh,
    }),
    /** Grafik gorunumde dugum konumu (gecmise yazilmaz). */
    savePosition: useMutation({
      mutationFn: ({ id, x, y }: { id: number; x: number; y: number }) =>
        api<CardDetail>(`/cards/${id}`, { method: 'PATCH', ...json({ graph_x: x, graph_y: y }) }),
      // Sadece grafigi tazele (kanban'i gereksiz yere yeniden cekme)
      onSuccess: () => qc.invalidateQueries({ queryKey: keys.graph(boardId), exact: true }),
    }),
    addDependency: useMutation({
      mutationFn: ({ id, dependsOn }: { id: number; dependsOn: number }) =>
        api<CardDetail>(`/cards/${id}/dependencies`, {
          method: 'POST',
          ...json({ depends_on_id: dependsOn }),
        }),
      onSettled: refresh,
    }),
    removeDependency: useMutation({
      mutationFn: ({ id, dependsOn }: { id: number; dependsOn: number }) =>
        api<CardDetail>(`/cards/${id}/dependencies/${dependsOn}`, { method: 'DELETE' }),
      onSettled: refresh,
    }),
    createLabel: useMutation({
      mutationFn: (data: { name: string; color: string }) =>
        api<Label>(`/boards/${boardId}/labels`, { method: 'POST', ...json(data) }),
      onSuccess: refresh,
    }),
  }
}

// ---------------- kart detay ----------------
export function useCardMutations(cardId: number, boardId: number) {
  const qc = useQueryClient()
  const refresh = () => {
    qc.invalidateQueries({ queryKey: keys.card(cardId) })
    qc.invalidateQueries({ queryKey: keys.activity(cardId) })
    qc.invalidateQueries({ queryKey: keys.board(boardId) })
    qc.invalidateQueries({ queryKey: keys.boards })
  }

  return {
    update: useMutation({
      mutationFn: (data: CardUpdate) =>
        api<CardDetail>(`/cards/${cardId}`, { method: 'PATCH', ...json(data) }),
      onSuccess: (card) => {
        qc.setQueryData(keys.card(cardId), card)
        refresh()
      },
    }),
    /** Tekrar kurali (RRULE) ya da null: tekrari durdur. */
    recurrence: useMutation({
      mutationFn: (rule: string | null) =>
        api<CardDetail>(`/cards/${cardId}/recurrence`, { method: 'PUT', ...json({ rule }) }),
      onSuccess: (card) => {
        qc.setQueryData(keys.card(cardId), card)
        refresh()
      },
    }),
    remove: useMutation({
      mutationFn: () => api<void>(`/cards/${cardId}`, { method: 'DELETE' }),
      onSuccess: () => {
        qc.removeQueries({ queryKey: keys.card(cardId) })
        qc.invalidateQueries({ queryKey: keys.board(boardId) })
        qc.invalidateQueries({ queryKey: keys.boards })
      },
    }),
    addNote: useMutation({
      mutationFn: (content: string) =>
        api<Note>(`/cards/${cardId}/notes`, { method: 'POST', ...json({ content }) }),
      onSuccess: refresh,
    }),
    updateNote: useMutation({
      mutationFn: ({ id, content }: { id: number; content: string }) =>
        api<Note>(`/notes/${id}`, { method: 'PATCH', ...json({ content }) }),
      onSuccess: refresh,
    }),
    deleteNote: useMutation({
      mutationFn: (id: number) => api<void>(`/notes/${id}`, { method: 'DELETE' }),
      onSuccess: refresh,
    }),
    addItem: useMutation({
      mutationFn: (text: string) =>
        api<ChecklistItem>(`/cards/${cardId}/checklist`, { method: 'POST', ...json({ text }) }),
      onSuccess: refresh,
    }),
    updateItem: useMutation({
      mutationFn: ({ id, ...data }: { id: number; text?: string; is_done?: boolean }) =>
        api<ChecklistItem>(`/checklist/${id}`, { method: 'PATCH', ...json(data) }),
      onSuccess: refresh,
    }),
    addSubtask: useMutation({
      mutationFn: (title: string) =>
        api<CardDetail>('/cards', { method: 'POST', ...json({ parent_id: cardId, title }) }),
      onSuccess: refresh,
    }),
    split: useMutation({
      mutationFn: (data: CardSplit) =>
        api<CardDetail>(`/cards/${cardId}/split`, { method: 'POST', ...json(data) }),
      onSuccess: refresh,
    }),
    addDependency: useMutation({
      mutationFn: (dependsOn: number) =>
        api<CardDetail>(`/cards/${cardId}/dependencies`, {
          method: 'POST',
          ...json({ depends_on_id: dependsOn }),
        }),
      onSuccess: refresh,
    }),
    removeDependency: useMutation({
      mutationFn: (dependsOn: number) =>
        api<CardDetail>(`/cards/${cardId}/dependencies/${dependsOn}`, { method: 'DELETE' }),
      onSuccess: refresh,
    }),
    deleteItem: useMutation({
      mutationFn: (id: number) => api<void>(`/checklist/${id}`, { method: 'DELETE' }),
      onSuccess: refresh,
    }),
  }
}
