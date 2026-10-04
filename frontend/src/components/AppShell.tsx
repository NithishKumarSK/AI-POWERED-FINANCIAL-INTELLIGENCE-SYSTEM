import { NavLink, Outlet } from 'react-router-dom'
import { useIdentity } from '../context/IdentityContext'

const navItems = [
  { to: '/predict', label: 'Predict' },
  { to: '/dashboard', label: 'Accuracy Dashboard' },
  { to: '/pending', label: 'Pending Predictions' },
]

export function AppShell() {
  const { name, signOut } = useIdentity()

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-sm font-bold text-white">
              AV
            </div>
            <span className="text-lg font-semibold text-slate-900">AlphaVerity</span>
          </div>
          <nav className="flex items-center gap-1">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `rounded-md px-3 py-2 text-sm font-medium transition ${
                    isActive ? 'bg-blue-50 text-blue-700' : 'text-slate-600 hover:bg-slate-100'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="flex items-center gap-3">
            <span className="text-sm text-slate-500">
              Signed in as <span className="font-medium text-slate-700">{name}</span>
            </span>
            <button
              onClick={signOut}
              className="rounded-md border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
            >
              Switch user
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">
        <Outlet />
      </main>
    </div>
  )
}
