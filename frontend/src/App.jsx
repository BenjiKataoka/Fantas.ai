import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import {
  Show, SignInButton, SignUpButton, UserButton, useAuth,
  ClerkLoading, ClerkLoaded,
} from '@clerk/react'
import Dashboard from './pages/Dashboard'
import NewsHub from './pages/NewsHub'
import PlayerTracker from './pages/PlayerTracker'
import StartSit from './pages/StartSit'
import Settings from './pages/Settings'
import Admin from './pages/Admin'
import Spinner from './components/Spinner'
import { setTokenGetter, getMe } from './services/api'

const NAV_LINKS = [
  { to: '/',         label: 'Dashboard' },
  { to: '/news',     label: 'News' },
  { to: '/tracker',  label: 'Tracker' },
  { to: '/startsit', label: 'Start/Sit' },
  { to: '/settings', label: 'Settings' },
]

function NavBar({ isAdmin }) {
  const links = isAdmin ? [...NAV_LINKS, { to: '/admin', label: 'Admin' }] : NAV_LINKS
  return (
    <nav className="bg-gray-900 border-b border-gray-700 px-6 py-3 flex items-center gap-6">
      <span className="text-white font-bold text-lg tracking-tight mr-4">Fantas.ai</span>
      {links.map(({ to, label }) => (
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
      <div className="ml-auto">
        <UserButton afterSignOutUrl="/" />
      </div>
    </nav>
  )
}

// ── Full-screen states ────────────────────────────────────────────────────────

function CenteredShell({ children }) {
  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 flex items-center justify-center px-6">
      <div className="max-w-md w-full text-center">{children}</div>
    </div>
  )
}

function Landing() {
  return (
    <CenteredShell>
      <h1 className="text-3xl font-bold text-white mb-2">Fantas.ai</h1>
      <p className="text-gray-400 mb-8">
        Multi-source fantasy football analytics — projections, AI news analysis, and start/sit.
      </p>
      <div className="flex items-center justify-center gap-3">
        <SignInButton mode="modal">
          <button className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold rounded-lg transition-colors">
            Sign in
          </button>
        </SignInButton>
        <SignUpButton mode="modal">
          <button className="px-5 py-2.5 bg-gray-800 hover:bg-gray-700 text-gray-200 text-sm font-semibold rounded-lg border border-gray-700 transition-colors">
            Create account
          </button>
        </SignUpButton>
      </div>
      <p className="text-xs text-gray-600 mt-6">New accounts require admin approval before access.</p>
    </CenteredShell>
  )
}

function PendingScreen() {
  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <div className="bg-gray-900 border-b border-gray-700 px-6 py-3 flex items-center">
        <span className="text-white font-bold text-lg tracking-tight">Fantas.ai</span>
        <div className="ml-auto"><UserButton afterSignOutUrl="/" /></div>
      </div>
      <CenteredShell>
        <div className="text-5xl mb-4">⏳</div>
        <h2 className="text-xl font-bold text-white mb-2">Awaiting approval</h2>
        <p className="text-gray-400">
          Your account was created and is pending admin approval. You'll have access as soon as
          you're approved.
        </p>
      </CenteredShell>
    </div>
  )
}

function ErrorScreen() {
  return (
    <CenteredShell>
      <div className="text-5xl mb-4">⚠️</div>
      <h2 className="text-xl font-bold text-white mb-2">Couldn't reach the server</h2>
      <p className="text-gray-400 mb-6">Something went wrong verifying your account. Try again.</p>
      <button
        onClick={() => window.location.reload()}
        className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-200 text-sm rounded-lg border border-gray-700"
      >
        Reload
      </button>
    </CenteredShell>
  )
}

// ── Authenticated app (post sign-in) ──────────────────────────────────────────

function AuthedApp() {
  const { getToken } = useAuth()
  // Register the token getter synchronously (before any child API call fires) so every
  // request carries the Clerk JWT. Idempotent module-level assignment.
  setTokenGetter(() => getToken())

  const [me, setMe] = useState(null)
  const [status, setStatus] = useState('loading') // loading | approved | pending | error

  useEffect(() => {
    let alive = true
    getMe()
      .then((res) => { if (alive) { setMe(res.data); setStatus('approved') } })
      .catch((err) => {
        if (!alive) return
        setStatus(err.response?.status === 403 ? 'pending' : 'error')
      })
    return () => { alive = false }
  }, [])

  if (status === 'loading') {
    return <CenteredShell><Spinner label="Verifying your account…" /></CenteredShell>
  }
  if (status === 'pending') return <PendingScreen />
  if (status === 'error') return <ErrorScreen />

  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-950 text-gray-100">
        <NavBar isAdmin={me?.is_admin} />
        <main className="max-w-7xl mx-auto px-6 py-8">
          <Routes>
            <Route path="/"         element={<Dashboard />} />
            <Route path="/news"     element={<NewsHub />} />
            <Route path="/tracker"  element={<PlayerTracker />} />
            <Route path="/startsit" element={<StartSit />} />
            <Route path="/settings" element={<Settings />} />
            {me?.is_admin && <Route path="/admin" element={<Admin />} />}
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

export default function App() {
  return (
    <>
      <ClerkLoading>
        <CenteredShell><Spinner label="Loading…" /></CenteredShell>
      </ClerkLoading>
      <ClerkLoaded>
        <Show when="signed-out"><Landing /></Show>
        <Show when="signed-in"><AuthedApp /></Show>
      </ClerkLoaded>
    </>
  )
}
