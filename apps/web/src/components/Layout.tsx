import { NavLink, Outlet, useMatch } from 'react-router-dom'
import {
  BarChart3,
  CalendarDays,
  LayoutGrid,
  LogOut,
  Settings,
  Moon,
  Sparkles,
  Sun,
  UserRound,
  type LucideIcon,
} from 'lucide-react'
import { useBoards } from '../api/boards'
import { useSaveTheme, useThemeSync } from '../hooks/useThemeSync'
import { oppositeTheme, useTheme } from '../lib/theme'
import { useAuthStore } from '../stores/auth'
import { useAssistantUi } from '../stores/assistant'
import AssistantPanel from './AssistantPanel'
import { useAutoInboxTriage } from './InboxTriage'
import Reminders from './Reminders'
import TimerWidget from './TimerWidget'

const NAV: { to: string; label: string; icon: LucideIcon; end?: boolean }[] = [
  { to: '/today', label: 'Bugün', icon: Sun },
  { to: '/calendar', label: 'Takvim', icon: CalendarDays },
  { to: '/', label: "Board'lar", icon: LayoutGrid, end: true },
  { to: '/stats', label: 'İstatistik', icon: BarChart3 },
  { to: '/profile', label: 'Profil', icon: UserRound },
]

const navClass = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-[15px] ${
    isActive
      ? 'bg-surface font-semibold text-slate-900 shadow-[0_0_0_1px_var(--color-slate-200)]'
      : 'text-slate-600 hover:bg-slate-100'
  }`

/**
 * Hayat alanlari, kagit ajandalarin kenarindaki renkli indeks sekmeleri gibi:
 * renk seridi rayin kenarina yapisik; secili alanin sekmesi kalinlasir.
 */
function AreaTabs() {
  const boards = useBoards()
  const match = useMatch('/boards/:boardId')
  const activeId = match ? Number(match.params.boardId) : null
  if (!boards.data?.length) return null
  return (
    <nav aria-label="Hayat alanları" className="mt-6">
      <p className="mb-1.5 pl-4 text-[13px] text-slate-500">Alanlar</p>
      <ul className="space-y-0.5">
        {boards.data.map((b) => {
          const active = b.id === activeId
          return (
            <li key={b.id} className="relative">
              <NavLink
                to={`/boards/${b.id}`}
                className={`group flex items-center gap-2 rounded-r-lg py-1.5 pr-2.5 pl-4 text-[15px] ${
                  active ? 'bg-surface font-semibold text-slate-900' : 'text-slate-700 hover:bg-slate-100'
                }`}
              >
                <span
                  aria-hidden
                  className={`absolute top-1 bottom-1 left-0 rounded-r-sm transition-[width] ${
                    active ? 'w-2' : 'w-1 group-hover:w-1.5'
                  }`}
                  style={{ backgroundColor: b.color }}
                />
                <span className="min-w-0 flex-1 truncate">{b.name}</span>
                {b.privacy === 'local_only' && <span className="sr-only">(sadece local model)</span>}
                {b.open_card_count > 0 && (
                  <span className="text-xs text-slate-500 tabular-nums">{b.open_card_count}</span>
                )}
              </NavLink>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}

export default function Layout() {
  const logout = useAuthStore((s) => s.logout)
  const assistantOpen = useAssistantUi((s) => s.open)
  const toggleAssistant = useAssistantUi((s) => s.toggle)
  useAutoInboxTriage()
  useThemeSync()
  const { resolved, paper } = useTheme()
  const themeSaver = useSaveTheme()
  return (
    // h-screen: icerik alani kesin yukseklik alir (React Flow %100 yukseklik ister,
    // kanban listeleri de sayfa yerine kendi iclerinde kayar)
    <div className="flex h-screen">
      <aside className="flex w-60 shrink-0 flex-col border-r border-slate-200 bg-slate-50 py-4 pr-3">
        <div className="mb-5 pl-4">
          <span className="text-[24px] leading-none font-[750] tracking-tight" style={{ fontFamily: 'var(--font-display)' }}>
            Ajanda
          </span>
          <p className="mt-1 text-xs text-slate-500">Yaşam planlayıcı</p>
        </div>

        <nav aria-label="Ana menü" className="space-y-0.5 pl-2">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} className={navClass}>
              <Icon size={17} strokeWidth={1.75} aria-hidden />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="min-h-0 flex-1 overflow-y-auto">
          <AreaTabs />
        </div>

        <div className="space-y-2 pt-3 pl-2">
          <TimerWidget />
          <button
            onClick={toggleAssistant}
            aria-pressed={assistantOpen}
            className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-[15px] ${
              assistantOpen ? 'bg-slate-900 text-on-ink' : 'text-slate-700 hover:bg-slate-100'
            }`}
          >
            <Sparkles size={17} strokeWidth={1.75} aria-hidden />
            Asistan
          </button>
          <div className="flex items-center gap-1 border-t border-slate-200 pt-2">
            <NavLink to="/settings" className={({ isActive }) => `${navClass({ isActive })} flex-1`}>
              <Settings size={17} strokeWidth={1.75} aria-hidden />
              Ayarlar
            </NavLink>
            <button
              onClick={() => themeSaver.set(oppositeTheme(resolved), paper)}
              title={resolved === 'dark' ? 'Açık temaya geç' : 'Koyu temaya geç'}
              aria-label={resolved === 'dark' ? 'Açık temaya geç' : 'Koyu temaya geç'}
              className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
            >
              {resolved === 'dark' ? <Sun size={17} strokeWidth={1.75} aria-hidden /> : <Moon size={17} strokeWidth={1.75} aria-hidden />}
            </button>
            <button
              onClick={logout}
              title="Çıkış yap"
              aria-label="Çıkış yap"
              className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
            >
              <LogOut size={17} strokeWidth={1.75} aria-hidden />
            </button>
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <Reminders />
        <div className="flex min-h-0 flex-1">
          <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto">
            <Outlet />
          </main>
          <AssistantPanel />
        </div>
      </div>
    </div>
  )
}
