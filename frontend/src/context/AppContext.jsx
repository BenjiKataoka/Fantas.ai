import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { useAuth } from '@clerk/react'
import { toast } from 'sonner'
import { getRoster, getSettings, updateSettings, getNews, getStartSit, setTokenGetter } from '../services/api'
import { balanceWeights } from '../utils/weights'

const LS_USERNAME = 'fantasai_sleeper_username'
const LS_LEAGUE   = 'fantasai_league_id'

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
    return username && leagueId ? { username, leagueId } : null
  })

  const saveCredentials = useCallback((username, leagueId) => {
    localStorage.setItem(LS_USERNAME, username)
    localStorage.setItem(LS_LEAGUE, leagueId)
    setCredentials({ username, leagueId })
  }, [])

  const clearCredentials = useCallback(() => {
    localStorage.removeItem(LS_USERNAME)
    localStorage.removeItem(LS_LEAGUE)
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

  const fetchRoster = useCallback(async (creds = credentials) => {
    if (!creds) return
    setRosterLoading(true)
    setRosterError(null)
    try {
      const res = await getRoster(creds.username, creds.leagueId)
      setRosterData(res.data)
      setLastRefresh(new Date())
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

  // ── News ───────────────────────────────────────────────────────────────────
  const [newsData, setNewsData]       = useState(null)
  const [newsLoading, setNewsLoading] = useState(false)

  const fetchNews = useCallback(async (forceRefresh = false) => {
    setNewsLoading(true)
    try {
      const res = await getNews(forceRefresh)
      setNewsData(res.data)
    } catch {
      // silently fail — news is optional
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
      const res = await getStartSit(wk)
      setStartSitData(res.data)
    } catch {
      // silently fail — start/sit is optional (e.g. no projections synced yet)
    } finally {
      setStartSitLoading(false)
    }
  }, [])

  // Auto-fetch start/sit once the roster (and its week) is available
  useEffect(() => {
    if (authed && credentials && rosterData && !startSitData) fetchStartSit(rosterData.week)
  }, [authed, credentials, rosterData]) // eslint-disable-line react-hooks/exhaustive-deps

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
      // Store ONLY weight keys — a stray response field would corrupt balanceWeights (→ NaN).
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
      // Credentials
      credentials, saveCredentials, clearCredentials,
      // Roster
      rosterData, rosterLoading, rosterError, lastRefresh, fetchRoster,
      // Weights
      weights, weightsLoaded, saving, saveError, updateWeight, saveWeights, setWeights,
      // News
      newsData, newsLoading, fetchNews,
      // Start/Sit
      startSitData, startSitLoading, fetchStartSit,
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
