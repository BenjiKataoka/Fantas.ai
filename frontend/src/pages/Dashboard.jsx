import { REVEAL } from '@/lib/utils'
import { useState, useMemo } from 'react'
import { getLeagues } from '../services/api'
import { useApp } from '../context/AppContext'
import RosterTable from '../components/RosterTable'
import WeightSlider from '../components/WeightSlider'
import AlertFeed from '../components/AlertFeed'
import { TableSkeleton } from '../components/Skeletons'

// ── Analyze-my-roster button ──────────────────────────────────────────────────
// State lives in AppContext so progress survives page navigation; this is just the UI.
function AnalyzeRosterButton() {
  const { analysis, runRosterAnalysis } = useApp()
  const running = analysis?.running

  return (
    <button
      onClick={runRosterAnalysis}
      disabled={running}
      className="px-3 py-1.5 bg-brand/15 hover:bg-brand/25 disabled:opacity-60 disabled:cursor-wait text-brand text-xs font-semibold rounded-lg border border-brand/30 transition-colors"
    >
      {running ? `Analyzing ${analysis.ready}/${analysis.total}` : 'Analyze roster'}
    </button>
  )
}

const btnPrimary = 'bg-brand hover:brightness-110 disabled:opacity-40 disabled:cursor-not-allowed text-brand-fg font-semibold rounded-lg transition-all'
const field = 'bg-raised border border-line rounded-lg px-3 py-2 text-sm text-content placeholder-subtle/60 focus:outline-none focus:border-brand'

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
        setLeagueId(`${list[0].platform}:${list[0].league_id}`)
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not find Sleeper user.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-md mx-auto mt-16 bg-surface border border-line rounded-xl p-8">
      <h2 className="text-xl font-display font-semibold text-content mb-1">Connect your league</h2>
      <p className="text-subtle text-sm mb-6">Enter your Sleeper username to get started.</p>

      <div className="flex gap-2 mb-4">
        <input
          type="text"
          placeholder="Sleeper username"
          value={username}
          onChange={e => setUsername(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && findLeagues()}
          className={`flex-1 ${field}`}
        />
        <button onClick={findLeagues} disabled={loading || !username.trim()} className={`px-4 py-2 text-sm ${btnPrimary}`}>
          {loading ? '...' : 'Find'}
        </button>
      </div>

      {error && <p className="text-bear text-sm mb-4">{error}</p>}

      {leagues.length > 0 && (
        <>
          <select value={leagueId} onChange={e => setLeagueId(e.target.value)} className={`w-full mb-4 ${field}`}>
            {leagues.map(l => <option key={`${l.platform}:${l.league_id}`} value={`${l.platform}:${l.league_id}`}>{l.name}{l.platform === 'ESPN' ? ' (ESPN)' : ''}</option>)}
          </select>
          <button onClick={() => { const [platform, id] = leagueId.split(':'); onComplete(username.trim(), id, platform) }} className={`w-full py-2 text-sm ${btnPrimary}`}>
            Load Roster
          </button>
        </>
      )}
    </div>
  )
}

// ── Top bar ───────────────────────────────────────────────────────────────────
function TopBar({ rosterData }) {
  const seasonType   = rosterData?.season_type
  const season       = rosterData?.season
  const week         = rosterData?.week
  const starters     = (rosterData?.roster || []).filter(p => p.is_starter)
  const totalPts     = starters.reduce((s, p) => s + (p.weighted_proj || 0), 0)
  const weekLabel    = !rosterData ? '-' : seasonType === 'off' ? `${season} Offseason` : `Week ${week} · ${season}`

  return (
    <div className="flex items-end justify-between mb-6 pb-4 border-b border-line">
      <div className="flex items-baseline gap-4">
        <span className="text-xl font-display font-semibold text-content tracking-tight">{weekLabel}</span>
        {rosterData && (
          <span className="text-sm text-subtle">
            {rosterData.total_players} players · {rosterData.starters} starters
            {totalPts > 0 && (
              <span className="text-bull ml-3 font-mono text-base font-bold tabular-nums">{totalPts.toFixed(1)}</span>
            )}
            {totalPts > 0 && <span className="text-subtle/60 ml-1 text-xs uppercase tracking-wide">proj pts</span>}
          </span>
        )}
      </div>
      <div className="flex items-center gap-3">
        {rosterData && <AnalyzeRosterButton />}
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
    <div className="bg-surface border border-line rounded-xl p-5">
      <h3 className="text-sm font-display font-semibold text-content mb-4">Projection Weights</h3>
      <div className="flex flex-col gap-5">
        <WeightSlider label="Sleeper"     value={weights.weight_sleeper} onChange={v => updateWeight('weight_sleeper', v)} />
        <WeightSlider label="ESPN"        value={weights.weight_espn}    onChange={v => updateWeight('weight_espn', v)} />
        <WeightSlider label="FantasyPros" value={weights.weight_fp}      onChange={v => updateWeight('weight_fp', v)} />
      </div>
      <div className="flex items-center justify-between mt-4 pt-3 border-t border-line">
        <span className={`text-xs font-mono ${sumOk ? 'text-subtle' : 'text-bear'}`}>Total: {sum}%</span>
        <button onClick={() => saveWeights(weights)} disabled={!sumOk || saving} className={`px-3 py-1 text-xs ${btnPrimary}`}>
          {saving ? 'Saving...' : 'Save'}
        </button>
      </div>
      {saveError && <p className="text-bear text-xs mt-2">{saveError}</p>}
    </div>
  )
}

// ── Main Dashboard ────────────────────────────────────────────────────────────
export default function Dashboard() {
  const {
    credentials, saveCredentials, clearCredentials,
    rosterData, rosterLoading, rosterError,
    newsData, newsLoading,
    startSitData,
  } = useApp()

  // { player_id → most recent news card } for the roster's News column
  const newsMap = useMemo(() => {
    if (!newsData?.news) return {}
    const map = {}
    for (const item of newsData.news) if (!map[item.player_id]) map[item.player_id] = item
    return map
  }, [newsData])

  // { player_id → { slot } } for the roster's Start/Sit column (bench → slot:null → SIT)
  const startSitMap = useMemo(() => {
    if (!startSitData) return {}
    const map = {}
    for (const p of startSitData.starters || []) map[p.player_id] = { slot: p.slot }
    for (const p of startSitData.bench || [])    map[p.player_id] = { slot: null }
    return map
  }, [startSitData])

  // { player_id → { name, position } } for AlertFeed labels
  const playerMap = useMemo(() => {
    if (!rosterData?.roster) return {}
    const map = {}
    for (const p of rosterData.roster) map[p.player_id] = { name: p.name, position: p.position }
    return map
  }, [rosterData])

  if (!credentials) {
    return <SetupForm onComplete={(username, leagueId, platform) => saveCredentials(username, leagueId, platform)} />
  }

  return (
    <div>
      {/* Wrap so the click event isn't passed as `creds` (would break the fetch). */}
      <div className={REVEAL}>
        <TopBar rosterData={rosterData} />
      </div>

      {rosterError && (
        <div className="mb-4 p-3 bg-bear/10 border border-bear/30 rounded-lg text-bear text-sm">
          {rosterError}{' '}
          <button onClick={clearCredentials} className="underline ml-1">Reset credentials</button>
        </div>
      )}

      <div className="flex gap-6 items-start">
        <div key={rosterData ? 'table' : 'loading'} className={`flex-1 min-w-0 ${REVEAL}`} style={{ animationDelay: '90ms' }}>
          {rosterLoading && !rosterData && <TableSkeleton rows={9} />}
          {rosterData && <RosterTable players={rosterData.roster} newsMap={newsMap} startSitMap={startSitMap} />}
        </div>

        <div className={`w-56 shrink-0 flex flex-col gap-4 ${REVEAL}`} style={{ animationDelay: '180ms' }}>
          <WeightSidebar />
          <div className="bg-surface border border-line rounded-xl p-5">
            <h3 className="text-sm font-display font-semibold text-content mb-3">Alerts</h3>
            {newsLoading && !newsData
              ? <p className="text-xs text-subtle">Loading news...</p>
              : <AlertFeed items={newsData?.news ?? []} playerMap={playerMap} />
            }
          </div>
        </div>
      </div>
    </div>
  )
}
