import { NavLink, Outlet } from 'react-router-dom'
import { useAuthStore } from '../stores/auth'

const link = ({ isActive }: { isActive: boolean }) =>
  `rounded-md px-3 py-1.5 text-sm ${isActive ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-200'}`

export default function Layout() {
  const logout = useAuthStore((s) => s.logout)
  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center gap-2 border-b border-slate-200 bg-white px-4 py-2">
        <span className="mr-4 font-semibold">Yaşam Planlayıcı</span>
        <NavLink to="/" end className={link}>
          Board'lar
        </NavLink>
        <NavLink to="/settings" className={link}>
          Ayarlar
        </NavLink>
        <button onClick={logout} className="ml-auto text-sm text-slate-500 hover:underline">
          Çıkış
        </button>
      </header>
      <main className="flex min-h-0 flex-1 flex-col">
        <Outlet />
      </main>
    </div>
  )
}
