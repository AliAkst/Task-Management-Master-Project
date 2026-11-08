import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface AssistantUi {
  open: boolean
  conversationId: number | null
  modelId: string | null // null = sunucunun varsayilani
  setOpen: (open: boolean) => void
  toggle: () => void
  setConversation: (id: number | null) => void
  setModel: (id: string | null) => void
}

/** Asistan panelinin durumu (acik/kapali, secili sohbet ve model) sayfalar arasi korunur. */
export const useAssistantUi = create<AssistantUi>()(
  persist(
    (set) => ({
      open: false,
      conversationId: null,
      modelId: null,
      setOpen: (open) => set({ open }),
      toggle: () => set((s) => ({ open: !s.open })),
      setConversation: (conversationId) => set({ conversationId }),
      setModel: (modelId) => set({ modelId }),
    }),
    { name: 'assistant-ui' },
  ),
)
