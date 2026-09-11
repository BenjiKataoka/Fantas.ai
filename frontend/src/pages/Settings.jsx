import { useState, useEffect } from 'react'
import { getLeagues } from '../services/api'
import { useApp } from '../context/AppContext'
import WeightSlider from '../components/WeightSlider'
import Spinner from '../components/Spinner'

function Section({ title, description, children }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
      <h2 className="text-base font-semibold text-white mb-1">{title}</h2>
      {description && <p className="text-sm text-gray-500 mb-5">{description}</p>}
      {children}
    </div>
  )
}

// ── Projection Weights ────────────────────────────────────────────────────────
function WeightsSection() {
  const { weights, weightsLoaded, saving, saveError, updateWeight, saveWeights } = useApp()
  const [saved, setSaved] = useState(false)
  const sum   = Math.round((weights.weight_sleeper + weights.weight_espn + weights.weight_fp) * 100)
  const sumOk = sum === 100

  const handleChange = (key, value) => {
    setSaved(false)
    updateWeight(key, value)
  }

  const handleSave = async () => {
    await saveWeights(weights)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <Section
      title="Projection Weights"
      description="Controls how Sleeper, ESPN, and FantasyPros projections are blended into the weighted score. Must total 100%."
    >
      {!weightsLoaded ? <Spinner label="Loading weights…" /> : (
        <div className="flex flex-col gap-5 max-w-sm">
          <WeightSlider label="Sleeper"     value={weights.weight_sleeper} onChange={v => handleChange('weight_sleeper', v)} />
          <WeightSlider label="ESPN"        value={weights.weight_espn}    onChange={v => handleChange('weight_espn', v)} />
          <WeightSlider label="FantasyPros" value={weights.weight_fp}      onChange={v => handleChange('weight_fp', v)} />
        </div>
      )}
      <div className="flex items-center gap-4 mt-6">
        <button
          onClick={handleSave}
          disabled={!sumOk || saving}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold rounded-lg transition-colors"
        >
          {saving ? 'Saving…' : saved ? 'Saved!' : 'Save Weights'}
        </button>
        <span className={`text-sm font-mono ${sumOk ? 'text-gray-500' : 'text-red-400'}`}>
          Total: {sum}%
        </span>
      </div>
      {saveError && <p className="text-red-400 text-sm mt-2">{saveError}</p>}
    </Section>
  )
}

// ── League Setup ──────────────────────────────────────────────────────────────
function LeagueSection() {
  const { credentials, saveCredentials } = useApp()
  const [username, setUsername]   = useState(credentials?.username || '')
  const [leagues, setLeagues]     = useState([])
  const [leagueId, setLeagueId]   = useState(credentials?.leagueId || '')
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState(null)
  const [saved, setSaved]         = useState(false)

  useEffect(() => {
    if (username) loadLeagues(username)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const loadLeagues = async (u) => {
    if (!u.trim()) return
    setLoading(true)
    setError(null)
    try {
      const res = await getLeagues(u.trim())
      const list = res.data.leagues || []
      setLeagues(list)
      // Keep current leagueId if it's still valid, else default to first
      if (!list.find(l => l.league_id === leagueId) && list.length) {
        setLeagueId(list[0].league_id)
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Sleeper user not found.')
      setLeagues([])
    } finally {
      setLoading(false)
    }
  }

  const handleSave = () => {
    if (!username || !leagueId) return
    saveCredentials(username.trim(), leagueId)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <Section
      title="League Setup"
      description="Your Sleeper username and the league to track on the Dashboard."
    >
      <div className="flex flex-col gap-3 max-w-sm">
        <div>
          <label className="block text-xs text-gray-500 mb-1">Sleeper Username</label>
          <div className="flex gap-2">
            <input
              type="text"
              value={username}
              onChange={e => { setUsername(e.target.value); setLeagues([]); setSaved(false) }}
              onKeyDown={e => e.key === 'Enter' && loadLeagues(username)}
              placeholder="your username"
              className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
            />
            <button
              onClick={() => loadLeagues(username)}
              disabled={loading || !username.trim()}
              className="px-3 py-2 bg-gray-700 hover:bg-gray-600 disabled:opacity-40 text-white text-sm rounded-lg transition-colors"
            >
              {loading ? '…' : 'Find'}
            </button>
          </div>
        </div>

        {error && <p className="text-red-400 text-sm">{error}</p>}

        {leagues.length > 0 && (
          <div>
            <label className="block text-xs text-gray-500 mb-1">Active League</label>
            <select
              value={leagueId}
              onChange={e => { setLeagueId(e.target.value); setSaved(false) }}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
            >
              {leagues.map(l => (
                <option key={l.league_id} value={l.league_id}>{l.name}</option>
              ))}
            </select>
          </div>
        )}

        <button
          onClick={handleSave}
          disabled={!username || !leagueId}
          className="w-fit px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold rounded-lg transition-colors"
        >
          {saved ? 'Saved!' : 'Save League'}
        </button>
      </div>
    </Section>
  )
}

// ── ESPN Credentials ──────────────────────────────────────────────────────────
function ESPNSection() {
  return (
    <Section
      title="ESPN Credentials"
      description="ESPN S2 cookie and SWID are required to sync your ESPN roster and projections."
    >
      <div className="flex items-start gap-3 p-3 bg-gray-800/50 border border-gray-700/50 rounded-lg max-w-sm">
        <span className="text-yellow-500 text-sm mt-0.5">⚠</span>
        <p className="text-sm text-gray-400">
          ESPN credentials are stored in server config until user authentication is set up in Phase 5.
          Your current credentials are active and working.
        </p>
      </div>
    </Section>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function Settings() {
  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold mb-6">Settings</h1>
      <div className="flex flex-col gap-5">
        <WeightsSection />
        <LeagueSection />
        <ESPNSection />
      </div>
    </div>
  )
}
