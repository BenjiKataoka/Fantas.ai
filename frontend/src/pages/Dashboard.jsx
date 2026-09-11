import { useState, useMemo } from 'react'
import { getLeagues } from '../services/api'
import { useApp } from '../context/AppContext'
import RosterTable from '../components/RosterTable'
import WeightSlider from '../components/WeightSlider'
import Spinner from '../components/Spinner'
import AlertFeed from '../components/AlertFeed'

// ── Setup form shown when no credentials in context ───────────────────────────
function SetupForm({ onComplete }) {
  const [username, setUsername] = useState('')
  const [leagues, setLeagues]   = useState([])
  const [leagueId, setLeagueId] = useState('')
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState(null)

  const findLeagues = async () => {
    if (!username.trim()) return
    setLoading(true)
    setError(null)
    try {
      const res = await getLeagues(username.trim())
      const list = res.data.leagues || []
      if (!list.length) {
        setError('No redraft PPR leagues found for this username.')
      } else {
        setLeagues(list)
        setLeagueId(list[0].league_id)
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not find Sleeper user.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-md mx-auto mt-16 bg-gray-900 border border-gray-700 rounded-xl p-8">
      <h2 className="text-xl font-bold mb-1">Connect your league</h2>
      <p className="text-gray-400 text-sm mb-6">Enter your Sleeper username to get started.</p>

      <div className="flex gap-2 mb-4">
        <input
          type="text"
          placeholder="Sleeper username"
          value={username}
          onChange={e => setUsername(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && findLeagues()}
          className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
        />
        <button
          onClick={findLeagues}
          disabled={loading || !username.trim()}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
        >
          {loading ? '...' : 'Find'}
        </button>
      </div>

      {error && <p className="text-red-400 text-sm mb-4">{error}</p>}

      {leagues.length > 0 && (
        <>
          <select
            value={leagueId}
            onChange={e => setLeagueId(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white mb-4 focus:outline-none focus:border-blue-500"
          >
            {leagues.map(l => (
              <option key={l.league_id} value={l.league_id}>{l.name}</option>
            ))}
          </select>
          <button
            onClick={() => onComplete(username.trim(), leagueId)}
            className="w-full py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold rounded-lg transition-colors"
          >
            Load Roster
          </button>
        </>
      )}
    </div>
  )
}

// ── Top bar ───────────────────────────────────────────────────────────────────
function TopBar({ rosterData, lastRefresh, onRefresh, loading }) {
  const seasonType   = rosterData?.season_type
  const season       = rosterData?.season
  const week         = rosterData?.week
  const starters     = (rosterData?.roster || []).filter(p => p.is_starter)
  const totalPts     = starters.reduce((s, p) => s + (p.weighted_proj || 0), 0)
  const weekLabel    = !rosterData ? '—' : seasonType === 'off' ? `${season} Offseason` : `Week ${week} · ${season}`
  const refreshLabel = lastRefresh ? lastRefresh.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : null

  return (
    <div className="flex items-center justify-between mb-6 pb-4 border-b border-gray-800">
      <div className="flex items-center gap-4">
        <span className="text-lg font-semibold text-white">{weekLabel}</span>
        {rosterData && (
          <span className="text-sm text-gray-500">
            {rosterData.total_players} players · {rosterData.starters} starters
            {totalPts > 0 && (
              <span className="text-green-400 ml-2 font-mono">{totalPts.toFixed(1)} pts projected</span>
            )}
          </span>
        )}
      </div>
      <div className="flex items-center gap-3">
        {refreshLabel && (
          <span className="text-xs text-gray-600">Updated {refreshLabel}</span>
        )}
        <button
          onClick={onRefresh}
          disabled={loading}
          className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-40 text-gray-300 text-xs font-medium rounded-lg border border-gray-700 transition-colors"
        >
          {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>
    </div>
  )
}

// ── Weight sliders sidebar ────────────────────────────────────────────────────
function WeightSidebar() {
  const { weights, weightsLoaded, saving, saveError, updateWeight, saveWeights } = useApp()
  if (!weightsLoaded) return null
  const sum   = Math.round((weights.weight_sleeper + weights.weight_espn + weights.weight_fp) * 100)
  const sumOk = sum === 100

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
      <h3 className="text-sm font-semibold text-white mb-4">Projection Weights</h3>
      <div className="flex flex-col gap-5">
        <WeightSlider label="Sleeper"     value={weights.weight_sleeper} onChange={v => updateWeight('weight_sleeper', v)} />
        <WeightSlider label="ESPN"        value={weights.weight_espn}    onChange={v => updateWeight('weight_espn', v)} />
        <WeightSlider label="FantasyPros" value={weights.weight_fp}      onChange={v => updateWeight('weight_fp', v)} />
      </div>
      <div className="flex items-center justify-between mt-4 pt-3 border-t border-gray-800">
        <span className={`text-xs font-mono ${sumOk ? 'text-gray-500' : 'text-red-400'}`}>
          Total: {sum}%
        </span>
        <button
          onClick={() => saveWeights(weights)}
          disabled={!sumOk || saving}
          className="px-3 py-1 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-semibold rounded-md transition-colors"
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>
      {saveError && <p className="text-red-400 text-xs mt-2">{saveError}</p>}
    </div>
  )
}

// ── Main Dashboard ────────────────────────────────────────────────────────────
export default function Dashboard() {
  const {
    credentials, saveCredentials, clearCredentials,
    rosterData, rosterLoading, rosterError, lastRefresh, fetchRoster,
    newsData, newsLoading,
  } = useApp()

  // { player_id → most recent news card } for RosterTable Latest News column
  const newsMap = useMemo(() => {
    if (!newsData?.news) return {}
    const map = {}
    for (const item of newsData.news) {
      if (!map[item.player_id]) map[item.player_id] = item
    }
    return map
  }, [newsData])

  // { player_id → { name, position } } for AlertFeed player labels
  const playerMap = useMemo(() => {
    if (!rosterData?.roster) return {}
    const map = {}
    for (const p of rosterData.roster) {
      map[p.player_id] = { name: p.name, position: p.position }
    }
    return map
  }, [rosterData])

  if (!credentials) {
    return <SetupForm onComplete={(username, leagueId) => saveCredentials(username, leagueId)} />
  }

  return (
    <div>
      <TopBar
        rosterData={rosterData}
        lastRefresh={lastRefresh}
        onRefresh={fetchRoster}
        loading={rosterLoading}
      />

      {rosterError && (
        <div className="mb-4 p-3 bg-red-900/30 border border-red-800 rounded-lg text-red-400 text-sm">
          {rosterError}{' '}
          <button onClick={clearCredentials} className="underline ml-1">Reset credentials</button>
        </div>
      )}

      <div className="flex gap-6 items-start">
        <div className="flex-1 min-w-0">
          {rosterLoading && !rosterData && <Spinner label="Loading roster…" />}
          {rosterData && <RosterTable players={rosterData.roster} newsMap={newsMap} />}
        </div>

        <div className="w-64 shrink-0 flex flex-col gap-4">
          <WeightSidebar />
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
            <h3 className="text-sm font-semibold text-white mb-3">Alerts</h3>
            {newsLoading && !newsData
              ? <p className="text-xs text-gray-600">Loading news…</p>
              : <AlertFeed items={newsData?.news ?? []} playerMap={playerMap} />
            }
          </div>
          <button
            onClick={clearCredentials}
            className="text-xs text-gray-600 hover:text-gray-400 transition-colors text-left"
          >
            Switch league
          </button>
        </div>
      </div>
    </div>
  )
}
