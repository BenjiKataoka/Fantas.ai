import { useEffect, useState } from 'react'
import { useApp } from '../context/AppContext'
import { getRecap } from '../services/api'
import PlayerAvatar from '../components/PlayerAvatar'
import { RecapSkeleton } from '../components/Skeletons'
import { REVEAL } from '@/lib/utils'

const SOURCE_NAMES = { sleeper: 'Sleeper', espn: 'ESPN', fp: 'FantasyPros', weighted: 'Your blend' }
const POS_COLORS = { QB: 'text-pos-qb', RB: 'text-pos-rb', WR: 'text-pos-wr', TE: 'text-pos-te' }

const fmt = (v) => (v == null ? '-' : v.toFixed(1))
const Num = ({ children, className = '' }) => <span className={`font-mono tabular-nums ${className}`}>{children}</span>

function Diff({ v }) {
  if (v == null) return <Num className="text-subtle/40">-</Num>
  const cls = v >= 3 ? 'text-bull' : v <= -3 ? 'text-bear' : 'text-subtle'
  return <Num className={cls}>{v > 0 ? '+' : ''}{v.toFixed(1)}</Num>
}

function PlayerRow({ p, inBest }) {
  return (
    <tr className="border-t border-line/50">
      <td className="px-3 py-2">
        <span className={`font-mono text-xs font-semibold ${POS_COLORS[p.position] || 'text-subtle'}`}>{p.position}</span>
      </td>
      <td className="px-3 py-2">
        <div className="flex items-center gap-2.5">
          <PlayerAvatar playerId={p.player_id} name={p.name} size="sm" />
          <span className="text-content">{p.name}</span>
          {!p.started && inBest && <span className="text-xs text-bull">should have started</span>}
        </div>
      </td>
      <td className="px-3 py-2 text-right"><Num className="text-subtle">{fmt(p.weighted_proj)}</Num></td>
      <td className="px-3 py-2 text-right"><Num className="text-content font-medium">{fmt(p.actual)}</Num></td>
      <td className="px-3 py-2 text-right"><Diff v={p.diff} /></td>
    </tr>
  )
}

function Summary({ d }) {
  const L = d.lineup
  const projGain = L.projection_lineup_points - L.your_points
  return (
    <p className="text-lg leading-relaxed text-content/90 max-w-2xl">
      You scored <Num className="text-content font-semibold">{L.your_points.toFixed(2)}</Num>.
      {L.points_left_on_bench > 0.5 ? (
        <> Your best lineup would have scored <Num className="text-content">{L.best_possible_points.toFixed(2)}</Num>,
          so <Num className="text-bear font-semibold">{L.points_left_on_bench.toFixed(1)}</Num> points sat on your bench.</>
      ) : (
        <> That was the best lineup your roster could have played.</>
      )}
      {Math.abs(projGain) >= 1 && (
        <> Starting whoever the projections liked would have scored <Num className="text-content">{L.projection_lineup_points.toFixed(2)}</Num>
          {projGain > 0 ? <>, <Num className="text-bull">{projGain.toFixed(1)}</Num> more.</> : <>, <Num className="text-bear">{(-projGain).toFixed(1)}</Num> fewer.</>}</>
      )}
    </p>
  )
}

function Accuracy({ d }) {
  const rows = Object.entries(d.accuracy).filter(([, a]) => a.n > 0)
  if (!rows.length) return null
  const worst = Math.max(...rows.map(([, a]) => a.mae))
  return (
    <div className="bg-surface border border-line rounded-xl p-5">
      <h2 className="font-display font-semibold text-content">How close were the projections?</h2>
      <p className="text-sm text-subtle mt-1 mb-4">Average miss per player this week. Shorter is better.</p>
      <div className="flex flex-col gap-3">
        {rows.sort((a, b) => a[1].mae - b[1].mae).map(([src, a]) => (
          <div key={src}>
            <div className="flex items-baseline justify-between text-sm">
              <span className={src === d.most_accurate_source ? 'text-content font-medium' : 'text-subtle'}>
                {SOURCE_NAMES[src]}{src === d.most_accurate_source && <span className="text-bull text-xs ml-2">closest</span>}
              </span>
              <span className="text-subtle"><Num className="text-content">{a.mae.toFixed(1)}</Num> pts <span className="text-xs">({a.n} players)</span></span>
            </div>
            <div className="h-1.5 mt-1.5 rounded-full bg-raised overflow-hidden">
              <div className={`h-full rounded-full ${src === d.most_accurate_source ? 'bg-bull' : 'bg-subtle/40'}`}
                   style={{ width: `${(a.mae / worst) * 100}%` }} />
            </div>
          </div>
        ))}
      </div>
      {rows.some(([s, a]) => s === 'fp' && a.n < 5) && (
        <p className="text-xs text-subtle mt-4">FantasyPros only publishes its top players per position, so it covers fewer of yours.</p>
      )}
    </div>
  )
}

export default function Recap() {
  const { credentials, rosterData } = useApp()
  const currentWeek = rosterData?.week
  const [week, setWeek] = useState(null)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => { if (currentWeek && week == null) setWeek(currentWeek) }, [currentWeek, week])

  useEffect(() => {
    if (!credentials || !week) return
    let cancelled = false
    setLoading(true); setError(null)
    getRecap(week, credentials.username, credentials.leagueId, credentials.platform)
      .then(res => { if (!cancelled) setData(res.data) })
      .catch(err => { if (!cancelled) { setData(null); setError(err.response?.data?.detail || 'Could not load this recap.') } })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [week, credentials])

  if (!credentials) return <p className="text-subtle text-sm py-16 text-center">Pick your league on the Dashboard first.</p>
  if (rosterData?.season_type === 'off') return <p className="text-subtle text-sm py-16 text-center">Recaps start once the season does.</p>

  const best = new Set(data?.lineup.best_lineup_ids || [])
  const starters = data?.players.filter(p => p.started) || []
  const bench = data?.players.filter(p => !p.started) || []

  return (
    <div className="max-w-5xl">
      <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-display font-bold text-content">Week {week ?? ''} recap</h1>
          {data?.league_name && <p className="text-sm text-subtle mt-0.5">{data.league_name}</p>}
        </div>
        {currentWeek && (
          <div className="flex gap-1">
            {Array.from({ length: currentWeek }, (_, i) => i + 1).map(w => (
              <button
                key={w}
                onClick={() => setWeek(w)}
                className={`px-2.5 py-1 rounded-md text-sm font-mono ${w === week ? 'bg-brand text-brand-fg' : 'text-subtle hover:text-content hover:bg-raised'}`}
              >
                {w}
              </button>
            ))}
          </div>
        )}
      </div>

      {!data && !error && <RecapSkeleton />}
      {error && <p className="text-bear text-sm">{error}</p>}

      {data && (
        <div key={data.week} className={`flex flex-col gap-6 transition-opacity ${loading ? 'opacity-50' : ''}`}>
          <div className={REVEAL}>
            {!data.final && (
              <p className="text-sm text-warn mb-2">This week isn't over yet, so these numbers will still move.</p>
            )}
            <Summary d={data} />
            {data.warning && <p className="text-sm text-warn mt-2">{data.warning}</p>}
          </div>

          <div className="grid lg:grid-cols-[1fr_320px] gap-6 items-start">
            <div className={`bg-surface border border-line rounded-xl overflow-hidden ${REVEAL}`} style={{ animationDelay: '90ms' }}>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-subtle text-xs">
                    <th className="px-3 py-2.5 text-left font-medium w-12">Pos</th>
                    <th className="px-3 py-2.5 text-left font-medium">Starters</th>
                    <th className="px-3 py-2.5 text-right font-medium">Projected</th>
                    <th className="px-3 py-2.5 text-right font-medium">Actual</th>
                    <th className="px-3 py-2.5 text-right font-medium">+/-</th>
                  </tr>
                </thead>
                <tbody>
                  {starters.map(p => <PlayerRow key={p.player_id} p={p} inBest={best.has(p.player_id)} />)}
                  <tr className="border-t border-line"><td colSpan={5} className="px-3 pt-4 pb-1.5 text-xs text-subtle">Bench</td></tr>
                  {bench.map(p => <PlayerRow key={p.player_id} p={p} inBest={best.has(p.player_id)} />)}
                </tbody>
              </table>
            </div>
            <div className={REVEAL} style={{ animationDelay: '180ms' }}><Accuracy d={data} /></div>
          </div>
        </div>
      )}
    </div>
  )
}
