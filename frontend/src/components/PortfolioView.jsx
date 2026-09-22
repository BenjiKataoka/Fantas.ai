import { useEffect, useMemo, useState } from 'react'
import { ChevronRight } from 'lucide-react'
import { useApp } from '../context/AppContext'
import { getMatchups, getPortfolio } from '../services/api'
import { WeekHero, LeagueStrip, LeagueStripSkeleton, MostOnTheLine, NeedsYou, YourSunday } from './WeekBoard'
import { REVEAL, slotLabel, tiltHandlers } from '@/lib/utils'
import { Hint } from '@/components/ui/tooltip'
import PlayerAvatar from './PlayerAvatar'
import InjuryBadge from './InjuryBadge'
import ProjectionBar from './ProjectionBar'
import AlertFeed from './AlertFeed'
import CollapseRow from './CollapseRow'
import { ConcernFlag } from './RosterTable'
import { TableSkeleton } from './Skeletons'

const POS_COLORS = { QB: 'text-pos-qb', RB: 'text-pos-rb', WR: 'text-pos-wr', TE: 'text-pos-te', K: 'text-subtle' }
const TH = 'px-3 py-2.5 text-left text-xs font-medium text-subtle'
const COLLAPSED = 8  // most-started players first, the rest behind "Show all"

// One mark per league you're in: filled = starting there, outlined = on the bench,
// faint = not on that team.
function ExposureMarks({ p, total }) {
  const marks = [
    ...p.leagues.map(l => (l.is_starter ? 'start' : 'bench')),
    ...Array(Math.max(0, total - p.held)).fill('none'),
  ]
  const cls = { start: 'bg-content', bench: 'border border-content/60', none: 'bg-line' }
  return (
    <div className="flex items-center gap-3">
      <Hint text="One dot per league. Filled: starting there. Outlined: on your bench. Faint: not on that team.">
        <span className="flex gap-1">
          {marks.map((m, i) => <span key={i} className={`size-2 rounded-full ${cls[m]}`} />)}
        </span>
      </Hint>
      <span className="text-xs text-subtle whitespace-nowrap">
        {p.held} of {total}{p.starting ? `, starting ${p.starting}` : ', all bench'}
      </span>
    </div>
  )
}

function LeagueList({ p }) {
  return (
    <ul className="px-5 py-3 grid gap-1.5 text-sm">
      {p.leagues.map(l => (
        <li key={`${l.platform}:${l.league_id}`} className="flex items-center gap-3">
          <span className={`w-14 shrink-0 font-mono text-xs ${l.is_starter ? 'text-bull' : 'text-subtle'}`}>
            {l.is_starter ? slotLabel(l.slot) : 'Bench'}
          </span>
          <span className="text-content/90 truncate">{l.name}</span>
          <span className="text-xs text-subtle">{l.platform === 'ESPN' ? 'ESPN' : 'Sleeper'}</span>
        </li>
      ))}
    </ul>
  )
}

function Row({ p, total, open, onToggle }) {
  return (
    <>
      <tr className="border-t border-line/50 hover:bg-raised/50 transition-colors cursor-pointer" onClick={onToggle} aria-expanded={open}>
        <td className="px-3 py-2.5">
          <div className="flex items-center gap-2.5">
            <ChevronRight className={`size-3.5 shrink-0 text-subtle/50 transition-transform ${open ? 'rotate-90 text-brand' : ''}`} />
            <PlayerAvatar playerId={p.player_id} name={p.name} size="md" />
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-medium text-content truncate">{p.name}</span>
                <InjuryBadge status={p.injury_status} />
              </div>
              <div className="text-xs text-subtle font-mono mt-0.5">{p.nfl_team || 'FA'}</div>
            </div>
            <ConcernFlag stock={p.stock} />
          </div>
        </td>
        <td className="px-3 py-2.5"><span className={`font-mono text-xs font-semibold ${POS_COLORS[p.position] || 'text-subtle'}`}>{p.position}</span></td>
        <td className="px-3 py-2.5 text-center"><ProjectionBar value={p.weighted_proj} injuryStatus={p.injury_status} strong /></td>
        <td className="px-3 py-2.5"><ExposureMarks p={p} total={total} /></td>
      </tr>
      <CollapseRow open={open} colSpan={4}><LeagueList p={p} /></CollapseRow>
    </>
  )
}

export default function PortfolioView({ onOpenLeague }) {
  const { credentials, lastRefresh, newsData } = useApp()
  const [data, setData] = useState(null)
  const [week, setWeek] = useState(null)
  const [error, setError] = useState(null)
  const [openId, setOpenId] = useState(null)
  const [showAll, setShowAll] = useState(false)

  // Two independent loads: this week's matchups (scoreboard, needs, kickoffs) and the
  // portfolio (players table). Both refetch whenever the roster re-syncs.
  useEffect(() => {
    if (!credentials) return
    let cancelled = false
    getMatchups(credentials.username)
      .then(res => { if (!cancelled) setWeek(res.data) })
      .catch(() => { if (!cancelled) setWeek(w => w || { leagues: [], needs: [], kickoffs: [], warnings: ['This week\'s matchups couldn\'t load.'] }) })
    getPortfolio(credentials.username)
      .then(res => { if (!cancelled) { setData(res.data); setError(null) } })
      .catch(err => { if (!cancelled) setError(err.response?.data?.detail || 'Could not load your portfolio.') })
    return () => { cancelled = true }
  }, [credentials, lastRefresh])

  const playerMap = useMemo(() => Object.fromEntries((data?.players || []).map(p => [p.player_id, { name: p.name, position: p.position }])), [data])
  const lineups = useMemo(() => Object.fromEntries((data?.players || []).map(p => [p.player_id, p.starting])), [data])

  const warnings = [...(week?.warnings || []), ...(data?.warnings || [])]
  const total = data?.summary.leagues
  return (
    <div className="flex flex-col gap-8">
      {week?.leagues?.length ? (
        <>
          <WeekHero data={week} />
          <LeagueStrip leagues={week.leagues} onOpen={onOpenLeague} />
          {/* Bento: wide cards on the left, narrow on the right; rows share a height. */}
          <div className={`grid grid-cols-1 lg:grid-cols-3 gap-4 ${REVEAL}`} style={{ animationDelay: '180ms' }}>
            <div className="lg:col-span-2"><NeedsYou needs={week.needs} leagues={week.leagues} /></div>
            <YourSunday windows={week.kickoffs} />
            <section aria-labelledby="alerts" {...tiltHandlers} className="lg:col-span-2 tilt h-full bg-surface border border-line rounded-xl p-6">
              <h2 id="alerts" className="font-display font-semibold text-2xl text-content mb-3">Alerts</h2>
              <AlertFeed items={newsData?.news ?? []} playerMap={playerMap} lineups={lineups} />
            </section>
            {data ? <MostOnTheLine players={data.players} /> : <div />}
          </div>
        </>
      ) : !week ? <LeagueStripSkeleton /> : null}
      {warnings.map(w => <p key={w} className="text-sm text-warn -mt-4">{w}</p>)}

      {error && !data && <p className="text-bear text-sm">{error}</p>}
      {!data && !error && <TableSkeleton rows={8} />}
      {data && (
      <div className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between">
        <h2 className="font-display font-semibold text-2xl text-content">Your players</h2>
        {data.summary.biggest_exposure && (
          <span className="text-sm text-subtle">Biggest exposure: {data.summary.biggest_exposure.name}, on {data.summary.biggest_exposure.held} of your {total} teams</span>
        )}
      </div>
      <div>
        <div className={`bg-surface border border-line rounded-xl ${REVEAL}`} style={{ animationDelay: '90ms' }}>
          <table className="w-full table-fixed text-sm">
            <colgroup><col /><col className="w-14" /><col className="w-24" /><col className="w-60" /></colgroup>
            <thead><tr><th className={TH}>Player</th><th className={TH}>Pos</th><th className={`${TH} text-center`}>Proj</th><th className={TH}>Your teams</th></tr></thead>
            <tbody>
              {(showAll ? data.players : data.players.slice(0, COLLAPSED)).map(p => (
                <Row key={p.player_id} p={p} total={total} open={openId === p.player_id}
                     onToggle={() => setOpenId(id => (id === p.player_id ? null : p.player_id))} />
              ))}
            </tbody>
          </table>
          {data.players.length > COLLAPSED && (
            <button
              type="button"
              onClick={() => setShowAll(v => !v)}
              aria-expanded={showAll}
              className="w-full py-3 border-t border-line text-sm font-medium text-subtle hover:text-content hover:bg-raised/50 rounded-b-xl"
            >
              {showAll ? 'Show fewer' : `Show all ${data.players.length} players`}
            </button>
          )}
        </div>
      </div>
      </div>
      )}
    </div>
  )
}
