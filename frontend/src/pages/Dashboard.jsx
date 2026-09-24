import { REVEAL } from '@/lib/utils'
import { useState, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { getLeagues } from '../services/api'
import { useApp } from '../context/AppContext'
import RosterTable from '../components/RosterTable'
import WeightSlider from '../components/WeightSlider'
import AlertFeed from '../components/AlertFeed'
import { TableSkeleton } from '../components/Skeletons'
import PortfolioView from '../components/PortfolioView'
import { LoadingDots } from '../components/Spinner'

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

  // ESPN-only: the server lists the leagues this account's saved cookies unlock.
  const findEspn = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getLeagues()
      const list = (res.data.leagues || []).filter(l => l.platform === 'ESPN')
      if (!list.length) {
        setError('No ESPN leagues yet. Connect your ESPN account in Settings, then come back.')
      } else {
        setLeagues(list)
        setLeagueId(`${list[0].platform}:${list[0].league_id}`)
      }
    } catch {
      setError('Could not reach ESPN. Connect your ESPN account in Settings first.')
    } finally {
      setLoading(false)
    }
  }

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
          {loading ? <LoadingDots /> : 'Find'}
        </button>
      </div>

      {error && (
        <p className="text-bear text-sm mb-4">
          {error}{' '}
          <Link to="/settings" className="underline underline-offset-2">Open Settings</Link>
        </p>
      )}

      {!leagues.length && !loading && (
        <div className="mt-6 pt-5 border-t border-line">
          <p className="text-sm text-subtle mb-3">Only play on ESPN? You don't need a Sleeper account.</p>
          <button onClick={findEspn} className="px-4 py-2 text-sm text-content border border-line rounded-lg hover:bg-raised">
            Use my ESPN leagues
          </button>
        </div>
      )}

      {leagues.length > 0 && (
        <>
          <select value={leagueId} onChange={e => setLeagueId(e.target.value)} className={`w-full mb-4 ${field}`}>
            {leagues.map(l => <option key={`${l.platform}:${l.league_id}`} value={`${l.platform}:${l.league_id}`}>{l.name}{l.platform === 'ESPN' ? ' (ESPN)' : ''}</option>)}
          </select>
          <button onClick={() => { const [platform, id] = leagueId.split(':'); onComplete(username.trim(), id, platform) }} className={`w-full py-2 text-sm ${btnPrimary}`}>
            Load roster
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
    <div className="flex flex-wrap items-end justify-between gap-y-3 mb-6 pb-4 border-b border-line">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <span className="text-xl font-display font-semibold text-content tracking-tight">{weekLabel}</span>
        {rosterData && (
          <span className="text-sm text-subtle">
            {rosterData.total_players} players · {rosterData.starters} starters
            {totalPts > 0 && (
              <span className="text-bull ml-3 font-mono text-base font-bold tabular-nums">{totalPts.toFixed(1)}</span>
            )}
            {totalPts > 0 && <span className="text-subtle/60 ml-1 text-xs">projected</span>}
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
          {saving ? <>Saving<LoadingDots /></> : 'Save'}
        </button>
      </div>
      {saveError && <p className="text-bear text-xs mt-2">{saveError}</p>}
    </div>
  )
}

// ── Portfolio / This league toggle ────────────────────────────────────────────
const VIEW_KEY = 'fantasai_dashboard_view'

function readView() {
  try { return localStorage.getItem(VIEW_KEY) || 'portfolio' } catch { return 'portfolio' }
}

function ViewToggle({ view, onChange, leagueName }) {
  const opt = (value, label) => (
    <button
      onClick={() => onChange(value)}
      aria-pressed={view === value}
      className={`px-3 py-1 rounded-md text-sm font-medium ${view === value ? 'bg-brand text-brand-fg' : 'text-subtle hover:text-content'}`}
    >
      {label}
    </button>
  )
  return (
    <div className="inline-flex gap-1 p-1 mb-6 rounded-lg bg-raised border border-line">
      {opt('portfolio', 'Portfolio')}
      {opt('league', leagueName ? `This league: ${leagueName}` : 'This league')}
    </div>
  )
}

// ── Main Dashboard ────────────────────────────────────────────────────────────
export default function Dashboard() {
  const {
    credentials, saveCredentials, clearCredentials,
    rosterData, rosterLoading, rosterError,
    newsData, newsLoading,
    startSitData, leagues, switchLeague,
  } = useApp()
  const [view, setView] = useState(readView)
  const chooseView = (v) => {
    setView(v)
    try { localStorage.setItem(VIEW_KEY, v) } catch { /* private mode: choice lasts this visit */ }
  }
  // The portfolio only means something with two or more leagues.
  const multi = leagues.length > 1
  const activeLeague = leagues.find(l => l.league_id === credentials?.leagueId && l.platform === credentials?.platform)

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

  if (multi && view === 'portfolio') {
    return (
      <div>
        <ViewToggle view={view} onChange={chooseView} leagueName={activeLeague?.name} />
        <PortfolioView onOpenLeague={(l) => { switchLeague(l.league_id, l.platform); chooseView('league') }} />
      </div>
    )
  }

  return (
    <div>
      {multi && <ViewToggle view={view} onChange={chooseView} leagueName={activeLeague?.name} />}
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

      <div className="flex flex-col lg:flex-row gap-6 items-start">
        <div key={rosterData ? 'table' : 'loading'} className={`w-full lg:flex-1 min-w-0 ${REVEAL}`} style={{ animationDelay: '90ms' }}>
          {rosterLoading && !rosterData && <TableSkeleton rows={9} />}
          {rosterData && <RosterTable players={rosterData.roster} newsMap={newsMap} startSitMap={startSitMap} />}
        </div>

        <div className={`w-full lg:w-56 shrink-0 flex flex-col gap-4 ${REVEAL}`} style={{ animationDelay: '180ms' }}>
          <WeightSidebar />
          <div className="bg-surface border border-line rounded-xl p-5">
            <h3 className="text-sm font-display font-semibold text-content mb-3">Alerts</h3>
            {newsLoading && !newsData
              ? <p className="text-xs text-subtle">Loading news<LoadingDots /></p>
              : <AlertFeed items={newsData?.news ?? []} playerMap={playerMap} />
            }
          </div>
        </div>
      </div>
    </div>
  )
}
