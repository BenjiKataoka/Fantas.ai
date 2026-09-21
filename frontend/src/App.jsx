import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, NavLink, useLocation } from 'react-router-dom'
import {
  Show, SignInButton, SignUpButton, UserButton,
  ClerkLoading, ClerkLoaded,
} from '@clerk/react'
import Dashboard from './pages/Dashboard'
import NewsHub from './pages/NewsHub'
import PlayerTracker from './pages/PlayerTracker'
import StartSit from './pages/StartSit'
import Settings from './pages/Settings'
import Admin from './pages/Admin'
import Spinner from './components/Spinner'
import Ticker from './components/Ticker'
import { getMe } from './services/api'

const NAV_LINKS = [
  { to: '/',         label: 'Dashboard' },
  { to: '/news',     label: 'News' },
  { to: '/tracker',  label: 'Tracker' },
  { to: '/startsit', label: 'Start/Sit' },
  { to: '/settings', label: 'Settings' },
]

function BrandMark({ className = '' }) {
  return (
    <span className={`font-display font-bold tracking-tight select-none ${className}`}>
      <span className="text-brand">◆</span> <span className="text-content">FANTAS</span><span className="text-brand">.</span><span className="text-content">AI</span>
    </span>
  )
}

function NavBar({ isAdmin }) {
  const links = isAdmin ? [...NAV_LINKS, { to: '/admin', label: 'Admin' }] : NAV_LINKS
  return (
    <nav className="bg-surface/80 backdrop-blur border-b border-line px-6 h-14 flex items-center gap-7">
      <BrandMark className="text-lg mr-3" />
      {links.map(({ to, label }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          className={({ isActive }) =>
            `text-sm font-medium h-14 flex items-center border-b-2 transition-colors ${
              isActive
                ? 'text-content border-brand'
                : 'text-subtle border-transparent hover:text-content'
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
    <div className="min-h-screen bg-ink flex items-center justify-center px-6">
      <div className="max-w-md w-full text-center">{children}</div>
    </div>
  )
}

function Landing() {
  return (
    <CenteredShell>
      <BrandMark className="text-4xl" />
      <p className="text-content text-lg font-display mt-5 mb-1">The player stock exchange.</p>
      <p className="text-subtle text-sm mb-8">
        Multi-source projections, AI news &amp; sentiment analysis, and weekly start/sit — for your redraft PPR league.
      </p>
      <div className="flex items-center justify-center gap-3">
        <SignInButton mode="modal">
          <button className="px-5 py-2.5 bg-brand hover:brightness-110 text-brand-fg text-sm font-semibold rounded-lg transition-all">
            Sign in
          </button>
        </SignInButton>
        <SignUpButton mode="modal">
          <button className="px-5 py-2.5 bg-raised hover:bg-line text-content text-sm font-semibold rounded-lg border border-line transition-colors">
            Create account
          </button>
        </SignUpButton>
      </div>
      <p className="text-xs text-subtle/70 mt-6">New accounts require admin approval before access.</p>
    </CenteredShell>
  )
}

function PendingScreen() {
  return (
    <div className="min-h-screen bg-ink">
      <div className="bg-surface/80 border-b border-line px-6 h-14 flex items-center">
        <BrandMark className="text-lg" />
        <div className="ml-auto"><UserButton afterSignOutUrl="/" /></div>
      </div>
      <CenteredShell>
        <div className="text-5xl mb-4">⏳</div>
        <h2 className="text-xl font-display font-semibold text-content mb-2">Awaiting approval</h2>
        <p className="text-subtle">
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
      <h2 className="text-xl font-display font-semibold text-content mb-2">Couldn't reach the server</h2>
      <p className="text-subtle mb-6">Something went wrong verifying your account. Try again.</p>
      <button
        onClick={() => window.location.reload()}
        className="px-4 py-2 bg-raised hover:bg-line text-content text-sm rounded-lg border border-line"
      >
        Reload
      </button>
    </CenteredShell>
  )
}

// Routed content, keyed on the path so each navigation replays a subtle enter
// transition (fade + slight rise). Pages read shared state from AppContext, so the
// per-route remount is cheap. Must live inside <BrowserRouter> to use useLocation.
function RoutedMain({ isAdmin }) {
  const location = useLocation()
  return (
    <main className="max-w-7xl mx-auto px-6 py-8">
      <div key={location.pathname} className="animate-in fade-in-0 slide-in-from-bottom-2 duration-300 ease-out">
        <Routes location={location}>
          <Route path="/"         element={<Dashboard />} />
          <Route path="/news"     element={<NewsHub />} />
          <Route path="/tracker"  element={<PlayerTracker />} />
          <Route path="/startsit" element={<StartSit />} />
          <Route path="/settings" element={<Settings />} />
          {isAdmin && <Route path="/admin" element={<Admin />} />}
        </Routes>
      </div>
    </main>
  )
}

// ── Authenticated app (post sign-in) ──────────────────────────────────────────

function AuthedApp() {
  // Token getter is registered in AppProvider (a parent), so requests here are authed.
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
      <div className="min-h-screen bg-ink text-content">
        <NavBar isAdmin={me?.is_admin} />
        <Ticker />
        <RoutedMain isAdmin={me?.is_admin} />
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
