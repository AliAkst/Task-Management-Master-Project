import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface AssistantUi {
  open: boolean
  conversationId: number | null
  modelId: string | null // null = sunucunun varsayilani
  // Baska bir sayfadan baslatilan sohbetin ilk mesaji (or. "Tanışalım"); panel gonderir
  pendingMessage: string | null
  setOpen: (open: boolean) => void
  toggle: () => void
  setConversation: (id: number | null) => void
  setModel: (id: string | null) => void
  startConversation: (message: string) => void
  takePendingMessage: () => string | null
}

/** Asistan panelinin durumu (acik/kapali, secili sohbet ve model) sayfalar arasi korunur. */
export const useAssistantUi = create<AssistantUi>()(
  persist(
    (set, get) => ({
      open: false,
      conversationId: null,
      modelId: null,
      pendingMessage: null,
      setOpen: (open) => set({ open }),
      toggle: () => set((s) => ({ open: !s.open })),
      setConversation: (conversationId) => set({ conversationId }),
      setModel: (modelId) => set({ modelId }),
      startConversation: (message) => set({ open: true, conversationId: null, pendingMessage: message }),
      takePendingMessage: () => {
        const message = get().pendingMessage
        if (message) set({ pendingMessage: null })
        return message
      },
    }),
    {
      name: 'assistant-ui',
      // Bekleyen mesaj kalici olmasin (sayfa yenilenince tekrar gonderilmesin)
      partialize: ({ open, conversationId, modelId }) => ({ open, conversationId, modelId }),
    },
  ),
)
