import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// Log errors centrally — individual hooks handle UI state
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

// --- Start/Sit ---
export const getStartSit = (week) => api.get(`/startsit/${week}`)

export default api
