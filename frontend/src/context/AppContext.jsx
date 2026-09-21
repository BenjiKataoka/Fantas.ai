import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react'
import { useAuth } from '@clerk/react'
import { toast } from 'sonner'
import { getRoster, getLeagues, getEspnStatus, getSettings, updateSettings, getNews, getStartSit, analyzeRoster, getRosterAnalysis, setTokenGetter } from '../services/api'
import { balanceWeights } from '../utils/weights'

const LS_USERNAME = 'fantasai_sleeper_username'
const LS_LEAGUE   = 'fantasai_league_id'
const LS_PLATFORM = 'fantasai_league_platform'
const STALE_MS    = 15 * 60 * 1000

const AppContext = createContext(null)

export function AppProvider({ children }) {
  // ── Auth readiness ───────────────────────────────────────────────────────────
  // Register the Clerk JWT getter and gate all auto-fetches on it, so requests never
  // fire before a token exists (avoids 401 "Missing bearer token" on startup).
  const { isLoaded, isSignedIn, getToken } = useAuth()
  const authed = isLoaded && isSignedIn
  // Register synchronously during render (parent renders before any child effect fires)
  // so the token is available before the approval gate or auto-fetches call the API.
  setTokenGetter(() => getToken())

  // ── Credentials ────────────────────────────────────────────────────────────
  const [credentials, setCredentials] = useState(() => {
    const username = localStorage.getItem(LS_USERNAME)
    const leagueId = localStorage.getItem(LS_LEAGUE)
    const platform = localStorage.getItem(LS_PLATFORM) || 'SLEEPER'
    return username && leagueId ? { username, leagueId, platform } : null
  })

  const saveCredentials = useCallback((username, leagueId, platform = 'SLEEPER') => {
    localStorage.setItem(LS_USERNAME, username)
    localStorage.setItem(LS_LEAGUE, leagueId)
    localStorage.setItem(LS_PLATFORM, platform)
    setCredentials({ username, leagueId, platform })
  }, [])

  const clearCredentials = useCallback(() => {
    localStorage.removeItem(LS_USERNAME)
    localStorage.removeItem(LS_LEAGUE)
    localStorage.removeItem(LS_PLATFORM)
    setCredentials(null)
    setRosterData(null)
    setStartSitData(null)
    setNewsData(null)
  }, [])

  // ── Roster ─────────────────────────────────────────────────────────────────
  const [rosterData, setRosterData]     = useState(null)
  const [rosterLoading, setRosterLoading] = useState(false)
  const [rosterError, setRosterError]   = useState(null)
  const [lastRefresh, setLastRefresh]   = useState(null)

  // force skips the server's 15-minute league cache (the manual refresh icon uses it).
  const fetchRoster = useCallback(async (creds = credentials, { force = false } = {}) => {
    if (!creds) return
    setRosterLoading(true)
    setRosterError(null)
    try {
      const res = await getRoster(creds.username, creds.leagueId, creds.platform, force)
      setRosterData(res.data)
      setLastRefresh(new Date())
      return res.data
    } catch (err) {
      setRosterError(err.response?.data?.detail || 'Failed to load roster.')
    } finally {
      setRosterLoading(false)
    }
  }, [credentials])

  // Auto-fetch roster once signed in and credentials are available
  useEffect(() => {
    if (authed && credentials && !rosterData) fetchRoster(credentials)
  }, [authed, credentials]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Leagues ────────────────────────────────────────────────────────────────
  // Every eligible league for this Sleeper account, for the navbar switcher.
  const [leagues, setLeagues] = useState([])

  const reloadLeagues = useCallback(() => {
    if (!credentials?.username) return
    getLeagues(credentials.username).then(res => setLeagues(res.data.leagues || [])).catch(() => {})
  }, [credentials?.username])

  useEffect(() => { if (authed) reloadLeagues() }, [authed, reloadLeagues])

  // Switching reloads the roster (which also syncs it server-side) and drops the old
  // league's start/sit; pages that read credentials.leagueId refetch on their own.
  // Switching takes the league's platform along, since Sleeper and ESPN load differently.
  const switchLeague = useCallback((leagueId, platform = 'SLEEPER') => {
    if (!credentials || (leagueId === credentials.leagueId && platform === credentials.platform)) return
    const next = { username: credentials.username, leagueId, platform }
    localStorage.setItem(LS_LEAGUE, leagueId)
    localStorage.setItem(LS_PLATFORM, platform)
    setCredentials(next)
    setRosterData(null)
    setStartSitData(null)
    fetchRoster(next)
  }, [credentials, fetchRoster])

  // ── News ───────────────────────────────────────────────────────────────────
  const [newsData, setNewsData]       = useState(null)
  const [newsLoading, setNewsLoading] = useState(false)

  const fetchNews = useCallback(async (forceRefresh = false) => {
    setNewsLoading(true)
    try {
      const res = await getNews(forceRefresh)
      setNewsData(res.data)
    } catch {
      // silently fail, news is optional
    } finally {
      setNewsLoading(false)
    }
  }, [])

  // Auto-fetch news after roster loads
  useEffect(() => {
    if (authed && credentials && rosterData && !newsData) fetchNews()
  }, [authed, credentials, rosterData]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Start/Sit ──────────────────────────────────────────────────────────────
  const [startSitData, setStartSitData]       = useState(null)
  const [startSitLoading, setStartSitLoading] = useState(false)

  const fetchStartSit = useCallback(async (week) => {
    // Offseason short-circuits server-side regardless of week; fall back to 1 if unknown
    const wk = Number.isInteger(week) ? week : 1
    setStartSitLoading(true)
    try {
      const res = await getStartSit(wk, credentials?.leagueId)
      setStartSitData(res.data)
    } catch {
      // silently fail, start/sit is optional (e.g. no projections synced yet)
    } finally {
      setStartSitLoading(false)
    }
  }, [credentials])

  // Auto-fetch start/sit once the roster (and its week) is available
  useEffect(() => {
    if (authed && credentials && rosterData && !startSitData) fetchStartSit(rosterData.week)
  }, [authed, credentials, rosterData]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── ESPN connection ────────────────────────────────────────────────────────
  // needs_reconnect flips on server-side whenever ESPN rejects the saved cookies (page load
  // or the 6-hour sync); it drives the app-wide reconnect banner.
  const [espnNeedsReconnect, setEspnNeedsReconnect] = useState(false)
  const refreshEspnStatus = useCallback(() => {
    getEspnStatus().then(res => setEspnNeedsReconnect(res.data.needs_reconnect)).catch(() => {})
  }, [])
  useEffect(() => { if (authed) refreshEspnStatus() }, [authed, refreshEspnStatus])
  // A roster load can be what discovers expired cookies, so re-check after any failure.
  useEffect(() => { if (authed && rosterError) refreshEspnStatus() }, [authed, rosterError, refreshEspnStatus])

  // ── Background refresh ─────────────────────────────────────────────────────
  // The roster (and the start/sit built on it) re-syncs in place: the current data stays
  // on screen, so no page needs a manual refresh. The server also syncs every 6h.
  const refreshAll = useCallback(async ({ force = false } = {}) => {
    const data = await fetchRoster(credentials, { force })
    if (data) fetchStartSit(data.week)
    refreshEspnStatus()
  }, [credentials, fetchRoster, fetchStartSit, refreshEspnStatus])

  // Coming back to a tab that's been idle 15+ minutes triggers a quiet refresh.
  useEffect(() => {
    if (!authed || !credentials) return
    const onReturn = () => {
      if (document.visibilityState !== 'visible' || rosterLoading) return
      if (lastRefresh && Date.now() - lastRefresh.getTime() < STALE_MS) return
      refreshAll()
    }
    document.addEventListener('visibilitychange', onReturn)
    window.addEventListener('focus', onReturn)
    return () => {
      document.removeEventListener('visibilitychange', onReturn)
      window.removeEventListener('focus', onReturn)
    }
  }, [authed, credentials, lastRefresh, rosterLoading, refreshAll])

  // ── Roster deep-dive analysis ────────────────────────────────────────────────
  // Lives in context (not the Dashboard) so progress survives page navigation and
  // a refresh mid-run resumes polling. The backend guards against duplicate runs.
  const [analysis, setAnalysis] = useState(null) // { running, ready, total, pending }
  const analysisTimer = useRef(null)

  const pollAnalysis = useCallback(function tick() {
    getRosterAnalysis()
      .then(async ({ data }) => {
        setAnalysis(data)
        if (data.running) {
          analysisTimer.current = setTimeout(tick, 4000)
        } else {
          analysisTimer.current = null
          await fetchRoster()               // surface freshly written stock profiles
          toast.success('Roster analysis complete.')
        }
      })
      .catch(() => { analysisTimer.current = setTimeout(tick, 4000) })
  }, [fetchRoster])

  const runRosterAnalysis = useCallback(async () => {
    if (analysis?.running) return
    try {
      const { data } = await analyzeRoster()
      if (data.status === 'empty') { toast.error('No roster to analyze yet.'); return }
      if (data.status === 'already_running') {
        toast.message('Analysis already in progress.')
        setAnalysis({ running: true, ready: 0, total: data.total, pending: data.total })
        pollAnalysis()
        return
      }
      if (data.queued === 0) {
        toast.success('All players already analyzed.')
        await fetchRoster()
        return
      }
      toast.success(`Analyzing ${data.queued} player${data.queued > 1 ? 's' : ''}...`)
      setAnalysis({ running: true, ready: data.skipped_fresh, total: data.total, pending: data.queued })
      pollAnalysis()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to start analysis.')
    }
  }, [analysis, fetchRoster, pollAnalysis])

  // Seed status when the roster loads; resume polling if a run is already in flight
  // (e.g. the user refreshed the page mid-analysis).
  useEffect(() => {
    if (!authed || !credentials || !rosterData) return
    let cancelled = false
    getRosterAnalysis()
      .then(({ data }) => {
        if (cancelled) return
        setAnalysis(data)
        if (data.running && !analysisTimer.current) pollAnalysis()
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [authed, credentials, rosterData]) // eslint-disable-line react-hooks/exhaustive-deps

  // Stop any pending poll on teardown
  useEffect(() => () => { if (analysisTimer.current) clearTimeout(analysisTimer.current) }, [])

  // ── Settings (weights) ─────────────────────────────────────────────────────
  const [weights, setWeights]       = useState({ weight_sleeper: 0.35, weight_espn: 0.30, weight_fp: 0.35 })
  const [weightsLoaded, setWeightsLoaded] = useState(false)
  const [saving, setSaving]         = useState(false)
  const [saveError, setSaveError]   = useState(null)

  useEffect(() => {
    if (!authed) return
    getSettings()
      .then(res => setWeights(res.data))
      .catch(() => {})
      .finally(() => setWeightsLoaded(true))
  }, [authed])

  const updateWeight = useCallback((key, value) => {
    setWeights(prev => balanceWeights(key, value, prev))
  }, [])

  const saveWeights = useCallback(async (newWeights) => {
    setSaving(true)
    setSaveError(null)
    try {
      const res = await updateSettings(newWeights)
      // Store ONLY weight keys, a stray response field would corrupt balanceWeights (→ NaN).
      const { weight_sleeper, weight_espn, weight_fp } = res.data
      setWeights({ weight_sleeper, weight_espn, weight_fp })
      toast.success('Projection weights saved')
      // Projections are computed server-side from the weights, so re-sync the roster
      // (recomputes them) and reset start/sit to refetch off the updated numbers.
      await fetchRoster()
      setStartSitData(null)
    } catch (err) {
      const msg = err.response?.data?.detail || 'Failed to save weights.'
      setSaveError(msg)
      toast.error(msg)
    } finally {
      setSaving(false)
    }
  }, [fetchRoster])

  return (
    <AppContext.Provider value={{
      // Credentials + leagues
      credentials, saveCredentials, clearCredentials, leagues, switchLeague, reloadLeagues,
      espnNeedsReconnect, refreshEspnStatus,
      // Roster
      rosterData, rosterLoading, rosterError, lastRefresh, fetchRoster, refreshAll,
      // Weights
      weights, weightsLoaded, saving, saveError, updateWeight, saveWeights, setWeights,
      // News
      newsData, newsLoading, fetchNews,
      // Start/Sit
      startSitData, startSitLoading, fetchStartSit,
      // Roster deep-dive analysis
      analysis, runRosterAnalysis,
    }}>
      {children}
    </AppContext.Provider>
  )
}

export function useApp() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp must be used inside AppProvider')
  return ctx
}
