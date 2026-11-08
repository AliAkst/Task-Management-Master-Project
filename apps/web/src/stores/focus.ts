import { create } from 'zustand'
import { persist } from 'zustand/middleware'

/** Odak suresi (pomodoro): null = kapali. Sure dolunca bildirim; kayit durmaz. */
interface FocusPrefs {
  focusMinutes: number | null
  setFocusMinutes: (m: number | null) => void
}

export const FOCUS_OPTIONS = [null, 25, 50] as const

export const useFocusPrefs = create<FocusPrefs>()(
  persist(
    (set) => ({
      focusMinutes: null,
      setFocusMinutes: (focusMinutes) => set({ focusMinutes }),
    }),
    { name: 'focus-prefs' },
  ),
)
