import { TriangleAlert, Hourglass, Sun, Moon, RotateCw, Menu, X } from 'lucide-react'
import { useTheme, setTheme } from '@/lib/theme'
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
import Recap from './pages/Recap'
import Waivers from './pages/Waivers'
import Tape from './pages/Tape'
import Settings from './pages/Settings'
import Admin from './pages/Admin'
import Spinner, { LoadingDots } from './components/Spinner'
import Ticker from './components/Ticker'
import { getMe } from './services/api'
import { useApp } from './context/AppContext'
import { relativeTime } from '@/lib/utils'

const NAV_LINKS = [
  { to: '/',         label: 'Dashboard' },
  { to: '/news',     label: 'News' },
  { to: '/tracker',  label: 'Tracker' },
  { to: '/startsit', label: 'Start/Sit' },
  { to: '/waivers',  label: 'Waivers' },
  { to: '/recap',    label: 'Recap' },
  { to: '/tape',     label: 'Tape' },
  { to: '/settings', label: 'Settings' },
]

function BrandMark({ className = '' }) {
  return (
    <span className={`inline-flex flex-col items-stretch select-none ${className}`}>
      <span className="font-display font-bold uppercase tracking-wide text-content leading-none">Fantas.ai</span>
      {/* The line to beat, the same device the scoreboard and waiver wire use. */}
      <span className="mt-1 h-[3px] rounded-full bg-mark" aria-hidden />
    </span>
  )
}

const PLATFORM_LABEL = { SLEEPER: 'Sleeper', ESPN: 'ESPN' }

// Value is "PLATFORM:league_id" so a Sleeper and an ESPN league can never collide.
function LeagueSwitcher({ className = 'max-w-56' }) {
  const { leagues, credentials, switchLeague } = useApp()
  if (leagues.length < 2 || !credentials) return null
  const platforms = [...new Set(leagues.map(l => l.platform))]
  const option = l => <option key={`${l.platform}:${l.league_id}`} value={`${l.platform}:${l.league_id}`}>{l.name}</option>
  return (
    <select
      aria-label="League"
      value={`${credentials.platform}:${credentials.leagueId}`}
      onChange={e => { const [platform, id] = e.target.value.split(':'); switchLeague(id, platform) }}
      className={`${className} truncate rounded-md bg-raised border border-line px-2.5 py-1 text-sm text-content focus:outline-none focus-visible:ring-2 focus-visible:ring-content/30`}
    >
      {platforms.length > 1
        ? platforms.map(p => <optgroup key={p} label={PLATFORM_LABEL[p]}>{leagues.filter(l => l.platform === p).map(option)}</optgroup>)
        : leagues.map(option)}
    </select>
  )
}

// Last roster sync plus a manual refresh. Refreshing normally happens on its own (tab
// return after 15 min, league switch, and the server's 6-hour sync).
function RefreshStatus() {
  const { lastRefresh, rosterLoading, refreshAll, credentials } = useApp()
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 30000)
    return () => clearInterval(id)
  }, [])
  if (!credentials) return null
  return (
    <div className="flex items-center gap-1.5 text-xs text-subtle">
      {rosterLoading
        ? <span className="flex items-center gap-2">Updating <LoadingDots /></span>
        : lastRefresh && <span className="font-mono">Updated {relativeTime(lastRefresh, now)}</span>}
      <button
        onClick={() => refreshAll({ force: true })}
        disabled={rosterLoading}
        aria-label="Refresh roster"
        title="Refresh roster"
        className="rounded-md p-1.5 hover:text-content hover:bg-raised disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-content/30"
      >
        <RotateCw className={`size-3.5 ${rosterLoading ? 'motion-safe:animate-spin' : ''}`} />
      </button>
    </div>
  )
}

// Shown on every page once ESPN starts rejecting the saved cookies, so the user finds out
// before an ESPN league quietly stops updating.
function EspnReconnectBanner() {
  const { espnNeedsReconnect } = useApp()
  if (!espnNeedsReconnect) return null
  return (
    <div role="status" className="bg-warn/10 border-b border-warn/30 px-6 py-2 text-sm text-content flex items-center gap-2">
      <TriangleAlert className="size-4 text-warn shrink-0" />
      <span>Your ESPN connection expired, so your ESPN leagues stopped updating.</span>
      <NavLink to="/settings" className="font-medium underline underline-offset-2 hover:text-warn">Reconnect in Settings</NavLink>
    </div>
  )
}

function ThemeToggle() {
  const theme = useTheme()
  const next = theme === 'dark' ? 'light' : 'dark'
  const Icon = theme === 'dark' ? Sun : Moon
  return (
    <button
      onClick={() => setTheme(next)}
      aria-label={`Switch to ${next} mode`}
      title={`Switch to ${next} mode`}
      className="rounded-md p-1.5 text-subtle hover:text-content hover:bg-raised focus:outline-none focus-visible:ring-2 focus-visible:ring-content/30"
    >
      <Icon className="size-4" />
    </button>
  )
}

function NavBar({ isAdmin }) {
  const links = isAdmin ? [...NAV_LINKS, { to: '/admin', label: 'Admin' }] : NAV_LINKS
  const [open, setOpen] = useState(false)
  const close = () => setOpen(false)

  useEffect(() => {
    if (!open) return
    const onKey = e => e.key === 'Escape' && setOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  return (
    // Nine links plus the switcher only fit on a wide screen; below xl they fold into a
    // menu panel instead of stretching every page past the edge of a phone.
    <nav className="relative z-40 bg-surface/80 backdrop-blur border-b border-line px-4 sm:px-6 h-14 flex items-center gap-7">
      <div className="flex items-center gap-3 xl:mr-3">
        <button
          onClick={() => setOpen(o => !o)}
          aria-expanded={open}
          aria-controls="nav-menu"
          aria-label={open ? 'Close menu' : 'Open menu'}
          className="xl:hidden -ml-1.5 rounded-md p-1.5 text-subtle hover:text-content hover:bg-raised focus:outline-none focus-visible:ring-2 focus-visible:ring-content/30"
        >
          {open ? <X className="size-5" /> : <Menu className="size-5" />}
        </button>
        <BrandMark className="text-lg" />
      </div>
      <div className="hidden xl:flex items-center gap-7">
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
      </div>
      <div className="ml-auto flex items-center gap-3">
        <div className="hidden xl:flex items-center gap-3">
          <RefreshStatus />
          <LeagueSwitcher />
        </div>
        <ThemeToggle />
        <UserButton afterSignOutUrl="/" />
      </div>

      {open && (
        <>
          {/* Tapping anywhere outside the panel closes it. Invisible on purpose: the panel's
              shadow separates it, and "ink" is the page colour, so it could not dim anyway. */}
          <button aria-hidden tabIndex={-1} onClick={close} className="xl:hidden fixed inset-0 top-14 cursor-default" />
          <div id="nav-menu" className="xl:hidden absolute left-0 right-0 top-full bg-surface border-b border-line shadow-lg">
            <div className="flex flex-col px-4 sm:px-6 py-2">
              {links.map(({ to, label }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={to === '/'}
                  onClick={close}
                  className={({ isActive }) =>
                    `py-3 text-base font-medium border-l-2 pl-3 transition-colors ${
                      isActive ? 'text-content border-brand' : 'text-subtle border-transparent hover:text-content'
                    }`
                  }
                >
                  {label}
                </NavLink>
              ))}
            </div>
            <div className="flex flex-col gap-3 px-4 sm:px-6 py-4 border-t border-line">
              <LeagueSwitcher className="w-full py-2" />
              <RefreshStatus />
            </div>
          </div>
        </>
      )}
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
      <p className="text-subtle text-sm mt-5 mb-8">
        Projections from three sources, news and sentiment tracking, and weekly start/sit calls for your redraft PPR league.
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
      <p className="text-xs text-subtle mt-6">New accounts require admin approval before access.</p>
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
        <Hourglass className="size-10 text-subtle mx-auto mb-4" />
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
      <TriangleAlert className="size-10 text-warn mx-auto mb-4" />
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
  // Pages with their own top-down section cascade skip the page-level fade.
  const plainEnter = ['/settings', '/admin'].includes(location.pathname)
  return (
    <main className="max-w-7xl mx-auto px-6 py-8">
      <div key={location.pathname} className={plainEnter ? 'animate-in fade-in-0 slide-in-from-bottom-2 duration-300 ease-out' : undefined}>
        <Routes location={location}>
          <Route path="/"         element={<Dashboard />} />
          <Route path="/news"     element={<NewsHub />} />
          <Route path="/tracker"  element={<PlayerTracker />} />
          <Route path="/startsit" element={<StartSit />} />
          <Route path="/recap"    element={<Recap />} />
          <Route path="/waivers"  element={<Waivers />} />
          <Route path="/tape"     element={<Tape />} />
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
    return <CenteredShell><Spinner label="Verifying your account" /></CenteredShell>
  }
  if (status === 'pending') return <PendingScreen />
  if (status === 'error') return <ErrorScreen />

  return (
    <BrowserRouter>
      <div className="min-h-screen bg-ink text-content">
        <NavBar isAdmin={me?.is_admin} />
        <EspnReconnectBanner />
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
        <CenteredShell><Spinner /></CenteredShell>
      </ClerkLoading>
      <ClerkLoaded>
        <Show when="signed-out"><Landing /></Show>
        <Show when="signed-in"><AuthedApp /></Show>
      </ClerkLoaded>
    </>
  )
}
