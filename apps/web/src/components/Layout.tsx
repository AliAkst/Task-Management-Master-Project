import { NavLink, Outlet } from 'react-router-dom'
import { useAuthStore } from '../stores/auth'
import Reminders from './Reminders'
import TimerWidget from './TimerWidget'

const link = ({ isActive }: { isActive: boolean }) =>
  `rounded-md px-3 py-1.5 text-sm ${isActive ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-200'}`

export default function Layout() {
  const logout = useAuthStore((s) => s.logout)
  return (
    // h-screen: icerik alani kesin yukseklik alir (React Flow %100 yukseklik ister,
    // kanban listeleri de sayfa yerine kendi iclerinde kayar)
    <div className="flex h-screen flex-col">
      <header className="flex items-center gap-2 border-b border-slate-200 bg-white px-4 py-2">
        <span className="mr-4 shrink-0 font-semibold whitespace-nowrap">Yaşam Planlayıcı</span>
        <NavLink to="/today" className={link}>
          Bugün
        </NavLink>
        <NavLink to="/" end className={link}>
          Board'lar
        </NavLink>
        <NavLink to="/calendar" className={link}>
          Takvim
        </NavLink>
        <NavLink to="/stats" className={link}>
          İstatistik
        </NavLink>
        <NavLink to="/settings" className={link}>
          Ayarlar
        </NavLink>
        <div className="ml-auto min-w-0">
          <TimerWidget />
        </div>
        <button onClick={logout} className="ml-2 text-sm text-slate-500 hover:underline">
          Çıkış
        </button>
      </header>
      <Reminders />
      <main className="flex min-h-0 flex-1 flex-col overflow-y-auto">
        <Outlet />
      </main>
    </div>
  )
}
