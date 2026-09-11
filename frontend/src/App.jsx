import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import NewsHub from './pages/NewsHub'
import PlayerTracker from './pages/PlayerTracker'
import StartSit from './pages/StartSit'
import Settings from './pages/Settings'

const NAV_LINKS = [
  { to: '/',         label: 'Dashboard' },
  { to: '/news',     label: 'News' },
  { to: '/tracker',  label: 'Tracker' },
  { to: '/startsit', label: 'Start/Sit' },
  { to: '/settings', label: 'Settings' },
]

function NavBar() {
  return (
    <nav className="bg-gray-900 border-b border-gray-700 px-6 py-3 flex items-center gap-6">
      <span className="text-white font-bold text-lg tracking-tight mr-4">Fantas.ai</span>
      {NAV_LINKS.map(({ to, label }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          className={({ isActive }) =>
            `text-sm font-medium transition-colors ${
              isActive ? 'text-white' : 'text-gray-400 hover:text-white'
            }`
          }
        >
          {label}
        </NavLink>
      ))}
    </nav>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-950 text-gray-100">
        <NavBar />
        <main className="max-w-7xl mx-auto px-6 py-8">
          <Routes>
            <Route path="/"         element={<Dashboard />} />
            <Route path="/news"     element={<NewsHub />} />
            <Route path="/tracker"  element={<PlayerTracker />} />
            <Route path="/startsit" element={<StartSit />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
