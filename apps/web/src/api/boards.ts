import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import type {
  Activity,
  Board,
  BoardCreate,
  BoardDetail,
  BoardList,
  BoardUpdate,
  BoardWithCounts,
  CardCreate,
  CardDetail,
  CardUpdate,
  ChecklistItem,
  Label,
  Note,
} from '../lib/types'

export const keys = {
  boards: ['boards'] as const,
  board: (id: number) => ['board', id] as const,
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
    deleteItem: useMutation({
      mutationFn: (id: number) => api<void>(`/checklist/${id}`, { method: 'DELETE' }),
      onSuccess: refresh,
    }),
  }
}
