import { create } from 'zustand'
import { persist } from 'zustand/middleware'

/** Cihaza ozel tercihler (sunucuda tutulmaz): sesli dikte ayarlari. */
interface Prefs {
  dictationEnabled: boolean
  dictationAutoSend: boolean // yalniz asistan paneli
  dictationNoticeSeen: boolean
  setDictationEnabled: (v: boolean) => void
  setDictationAutoSend: (v: boolean) => void
  markDictationNoticeSeen: () => void
}

export const usePrefs = create<Prefs>()(
  persist(
    (set) => ({
      dictationEnabled: true,
      dictationAutoSend: false,
      dictationNoticeSeen: false,
      setDictationEnabled: (dictationEnabled) => set({ dictationEnabled }),
      setDictationAutoSend: (dictationAutoSend) => set({ dictationAutoSend }),
      markDictationNoticeSeen: () => set({ dictationNoticeSeen: true }),
    }),
    { name: 'prefs' },
  ),
)
