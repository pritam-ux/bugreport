import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import {
  BarChart3, Bug, ClipboardCheck, CopyCheck, LayoutDashboard, Menu, PlusCircle, Users, X,
} from 'lucide-react'
import { useApi } from '../api/client.js'
import { Notice } from './ui.jsx'

const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/submit', label: 'Submit a bug', icon: PlusCircle },
  { to: '/bugs', label: 'All bugs', icon: Bug },
  { to: '/duplicates', label: 'Duplicate detection', icon: CopyCheck },
  { to: '/triage', label: 'AI triage', icon: ClipboardCheck },
  { to: '/developers', label: 'Developers', icon: Users },
  { to: '/analytics', label: 'AI analytics', icon: BarChart3 },
]

export const Logo = ({ light = true }) => (
  <span className={`flex items-center gap-2.5 text-[17px] font-semibold tracking-tight ${light ? 'text-white' : 'text-ink'}`}>
    <img src="/favicon.svg" alt="" width="28" height="28" />
    BugSense AI
  </span>
)

function EngineWarning() {
  const { data } = useApi('/system/status')
  if (!data) return null
  if (!data.semantic_available) {
    return (
      <Notice tone="warning" title="Semantic matching is off. Results use the TF-IDF baseline.">
        {data.semantic_error} Matches will miss reports that use different wording.
      </Notice>
    )
  }
  if (!data.classifiers_trained) {
    return (
      <Notice tone="warning" title="Classifiers are not trained, so reports get no predictions.">
        Run <code>python -m scripts.train</code> in the backend folder, then restart the API.
      </Notice>
    )
  }
  return null
}

export default function Layout() {
  const [menuOpen, setMenuOpen] = useState(false)
  const location = useLocation()

  useEffect(() => setMenuOpen(false), [location.pathname])

  return (
    <div className="min-h-full lg:pl-64">
      <div className="sticky top-0 z-30 flex items-center justify-between bg-navy-900 px-4 py-3 lg:hidden">
        <Logo />
        <button
          type="button"
          onClick={() => setMenuOpen(true)}
          aria-label="Open navigation"
          aria-expanded={menuOpen}
          className="rounded p-1.5 text-white hover:bg-navy-800"
        >
          <Menu size={22} aria-hidden />
        </button>
      </div>

      {menuOpen && <div className="fixed inset-0 z-40 bg-navy-950/50 lg:hidden" onClick={() => setMenuOpen(false)} aria-hidden />}

      <aside
        className={`sidebar-surface fixed inset-y-0 left-0 z-50 flex w-64 flex-col text-navy-300 transition-transform duration-200 lg:translate-x-0 ${
          menuOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex items-center justify-between px-5 py-5">
          <Logo />
          <button type="button" onClick={() => setMenuOpen(false)} aria-label="Close navigation" className="rounded p-1 text-white lg:hidden">
            <X size={20} aria-hidden />
          </button>
        </div>
        <nav aria-label="Main" className="flex-1 space-y-0.5 overflow-y-auto px-3">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                  isActive ? 'bg-white/10 text-white shadow-[inset_2px_0_0_#7f9bff]' : 'hover:bg-white/5 hover:text-white'
                }`
              }
            >
              <Icon size={18} aria-hidden />
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <main className="mx-auto max-w-[1320px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
        <div className="mb-4 empty:hidden"><EngineWarning /></div>
        <div key={location.pathname.split('/')[1]} className="view-enter">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
