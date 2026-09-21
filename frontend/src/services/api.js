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
  api.get('/leagues', { params: { sleeper_username: sleeperUsername } })

export const getRoster = (sleeperUsername, leagueId) =>
  api.get('/roster', { params: { sleeper_username: sleeperUsername, league_id: leagueId } })

// --- Projections ---
export const getProjections = (week) => api.get(`/projections/${week}`)

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
export const getTrackerDetail = (playerId) => api.get(`/tracker/${playerId}`)
export const starPlayer = (playerId) => api.post(`/tracker/star/${playerId}`)
export const unstarPlayer = (playerId) => api.delete(`/tracker/star/${playerId}`)
export const refreshPlayer = (playerId) => api.post(`/tracker/refresh/${playerId}`)
export const analyzeRoster = (force = false) => api.post('/tracker/analyze-roster', null, { params: { force } })
export const getRosterAnalysis = () => api.get('/tracker/roster-analysis')
export const getSentimentHistory = (playerId, range = 'season') =>
  api.get(`/tracker/${playerId}/sentiment-history`, { params: { range } })

// --- Start/Sit ---
export const getStartSit = (week) => api.get(`/startsit/${week}`)

// --- Auth / Admin ---
export const getMe = () => api.get('/me')
export const getAdminUsers = () => api.get('/admin/users')
export const approveUser = (userId) => api.post(`/admin/approve/${userId}`)
export const revokeUser = (userId) => api.post(`/admin/revoke/${userId}`)

export default api
