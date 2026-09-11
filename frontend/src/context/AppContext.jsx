import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { getRoster, getSettings, updateSettings, getNews } from '../services/api'
import { balanceWeights } from '../utils/weights'

const LS_USERNAME = 'fantasai_sleeper_username'
const LS_LEAGUE   = 'fantasai_league_id'

const AppContext = createContext(null)

export function AppProvider({ children }) {
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

  // Auto-fetch roster when credentials become available
  useEffect(() => {
    if (credentials && !rosterData) fetchRoster(credentials)
  }, [credentials]) // eslint-disable-line react-hooks/exhaustive-deps

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
    if (credentials && rosterData && !newsData) fetchNews()
  }, [credentials, rosterData]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Settings (weights) ─────────────────────────────────────────────────────
  const [weights, setWeights]       = useState({ weight_sleeper: 0.35, weight_espn: 0.30, weight_fp: 0.35 })
  const [weightsLoaded, setWeightsLoaded] = useState(false)
  const [saving, setSaving]         = useState(false)
  const [saveError, setSaveError]   = useState(null)

  useEffect(() => {
    getSettings()
      .then(res => setWeights(res.data))
      .catch(() => {})
      .finally(() => setWeightsLoaded(true))
  }, [])

  const updateWeight = useCallback((key, value) => {
    setWeights(prev => balanceWeights(key, value, prev))
  }, [])

  const saveWeights = useCallback(async (newWeights) => {
    setSaving(true)
    setSaveError(null)
    try {
      const res = await updateSettings(newWeights)
      setWeights(res.data)
    } catch (err) {
      setSaveError(err.response?.data?.detail || 'Failed to save weights.')
    } finally {
      setSaving(false)
    }
  }, [])

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
