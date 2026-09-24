import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// Clerk token injection, a component inside <ClerkProvider> registers getToken here,
// and every request attaches the current session JWT for the backend to verify.
let _tokenGetter = null
export function setTokenGetter(fn) {
  _tokenGetter = fn
}

api.interceptors.request.use(async (config) => {
  if (_tokenGetter) {
    try {
      const token = await _tokenGetter()
      if (token) config.headers.Authorization = `Bearer ${token}`
    } catch {
      // no token available (signed out), request goes through unauthenticated
    }
  }
  return config
})

// Log errors centrally, individual hooks handle UI state
api.interceptors.response.use(
  (res) => res,
  (err) => {
    console.error('[API]', err.config?.url, err.response?.status, err.message)
    return Promise.reject(err)
  }
)

// --- Roster ---
export const getLeagues = (sleeperUsername) =>
  api.get('/leagues', { params: sleeperUsername ? { sleeper_username: sleeperUsername } : {} })

export const getRoster = (sleeperUsername, leagueId, platform = 'SLEEPER', force = false) =>
  api.get('/roster', { params: { sleeper_username: sleeperUsername, league_id: leagueId, platform, force } })

// --- Projections ---

// --- Settings ---
export const getSettings = () => api.get('/settings')
export const updateSettings = (settings) => api.put('/settings', settings)

// --- News ---
export const getNews = (forceRefresh = false) =>
  api.get('/news', { params: { force_refresh: forceRefresh } })

// --- Players ---
export const searchPlayers = (q) => api.get('/players/search', { params: { q } })

// --- Tracker ---
export const getTrackerList = () => api.get('/tracker')
export const starPlayer = (playerId) => api.post(`/tracker/star/${playerId}`)
export const unstarPlayer = (playerId) => api.delete(`/tracker/star/${playerId}`)
export const analyzeRoster = (force = false) => api.post('/tracker/analyze-roster', null, { params: { force } })
export const getRosterAnalysis = () => api.get('/tracker/roster-analysis')
export const getSentimentHistory = (playerId, range = 'season') =>
  api.get(`/tracker/${playerId}/sentiment-history`, { params: { range } })

// --- Start/Sit ---
export const getStartSit = (week, leagueId) => api.get(`/startsit/${week}`, { params: { league_id: leagueId } })

// --- Recap ---
export const getRecap = (week, sleeperUsername, leagueId, platform = 'SLEEPER') =>
  api.get(`/recap/${week}`, { params: { sleeper_username: sleeperUsername, league_id: leagueId, platform } })

export const getWaivers = (sleeperUsername, leagueId, platform = 'SLEEPER') =>
  api.get('/waivers', { params: { sleeper_username: sleeperUsername, league_id: leagueId, platform } })

export const analyzeFreeAgent = (playerId, sleeperUsername, leagueId, platform = 'SLEEPER') =>
  api.post(`/waivers/analyze/${playerId}`, null, { params: { sleeper_username: sleeperUsername, league_id: leagueId, platform } })

export const getResults = (sleeperUsername, week) =>
  api.get('/results', { params: { sleeper_username: sleeperUsername, week } })

export const getMatchups = (sleeperUsername) =>
  api.get('/matchups', { params: { sleeper_username: sleeperUsername } })

export const getPortfolio = (sleeperUsername) =>
  api.get('/portfolio', { params: { sleeper_username: sleeperUsername } })

// --- ESPN account (cookies are write-only: the API never returns them) ---
export const getEspnStatus = () => api.get('/settings/espn')
export const saveEspn = (espn_s2, swid) => api.put('/settings/espn', { espn_s2, swid })
export const removeEspn = () => api.delete('/settings/espn')
export const removeSleeper = () => api.delete('/settings/sleeper')
export const lookupEspnLeague = (league) => api.post('/leagues/espn/lookup', { league })
export const addPublicEspnLeague = (leagueId, teamId) => api.post('/leagues/espn/public', { league_id: leagueId, team_id: teamId })
export const removeEspnLeague = (leagueId) => api.delete(`/leagues/espn/${leagueId}`)

// --- Auth / Admin ---
export const getMe = () => api.get('/me')
export const getAdminUsers = () => api.get('/admin/users')
export const approveUser = (userId) => api.post(`/admin/approve/${userId}`)
export const revokeUser = (userId) => api.post(`/admin/revoke/${userId}`)

export default api

export const getTape = (week) => api.get('/tape', { params: week ? { week } : {} })
