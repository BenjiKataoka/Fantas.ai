import { REVEAL, slotLabel } from '@/lib/utils'
import { useApp } from '../context/AppContext'
import InjuryBadge from '../components/InjuryBadge'
import PlayerAvatar from '../components/PlayerAvatar'
import { TableSkeleton } from '../components/Skeletons'

const SLOT_ORDER = { QB: 0, RB: 1, WR: 2, TE: 3, FLEX: 4, WRRB_FLEX: 4, REC_FLEX: 4, SUPER_FLEX: 5, K: 6, DEF: 7 }

// Position/slot tints kept clear of the bull-green / bear-red market colors.
const SLOT_COLORS = {
  QB:   'text-pos-qb',
  RB:   'text-pos-rb',
  WR:   'text-pos-wr',
  TE:   'text-pos-te',
  FLEX: 'text-brand', SUPER_FLEX: 'text-brand', WRRB_FLEX: 'text-brand', REC_FLEX: 'text-brand',
  K:    'text-subtle',
}

function projColor(v) {
  if (v == null) return 'text-subtle/40'
  if (v >= 15)   return 'text-bull'
  if (v >= 8)    return 'text-warn'
  return 'text-bear'
}

const H2 = 'text-sm font-display font-semibold text-subtle uppercase tracking-wider'

function LineupRow({ p }) {
  return (
    <tr className="hover:bg-raised/50 transition-colors">
      <td className="px-3 py-2.5">
        <span className={`font-mono font-semibold text-xs uppercase tracking-wide ${SLOT_COLORS[p.slot] || 'text-subtle'}`}>
          {slotLabel(p.slot)}
        </span>
      </td>
      <td className="px-3 py-2.5">
        <div className="flex items-center gap-2.5">
          <PlayerAvatar playerId={p.player_id} name={p.name} size="md" />
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-medium text-content">{p.name}</span>
              <InjuryBadge status={p.injury_status} />
            </div>
            <div className="text-xs text-subtle font-mono mt-0.5">{p.position} · {p.nfl_team}</div>
          </div>
        </div>
      </td>
      <td className="px-3 py-2.5 text-right font-mono tabular-nums text-sm font-medium">
        <span className={projColor(p.adjusted_proj)}>
          {p.adjusted_proj != null ? p.adjusted_proj.toFixed(1) : '-'}
        </span>
      </td>
    </tr>
  )
}

function CloseDecision({ d }) {
  return (
    <div className="bg-warn/8 border border-warn/25 rounded-lg p-3">
      <div className="flex items-center gap-2 mb-2">
        <span className={`font-mono text-xs font-semibold uppercase ${SLOT_COLORS[d.slot] || 'text-subtle'}`}>{slotLabel(d.slot)}</span>
        <span className="text-xs text-warn/80 font-mono">margin {d.margin.toFixed(1)}</span>
      </div>
      <div className="flex items-center gap-2 text-sm">
        <span className="text-bull font-medium">{d.start.name}</span>
        <span className="text-subtle text-xs font-mono">{d.start.adjusted_proj?.toFixed(1)}</span>
        <span className="text-subtle/60 mx-1">over</span>
        <span className="text-subtle">{d.sit.name}</span>
        <span className="text-subtle/60 text-xs font-mono">{d.sit.adjusted_proj?.toFixed(1)}</span>
      </div>
      <p className="text-xs text-warn/70 mt-1.5">{d.note}</p>
    </div>
  )
}

function PageTitle({ children }) {
  return <h1 className="text-2xl font-display font-bold text-content mb-2">{children}</h1>
}

export default function StartSit() {
  const { credentials, startSitData, startSitLoading } = useApp()

  if (!credentials) {
    return <div><PageTitle>Start / Sit</PageTitle><p className="text-subtle">Connect your league on the Dashboard to see lineup recommendations.</p></div>
  }

  if (startSitLoading && !startSitData) {
    return <div><PageTitle>Start / Sit</PageTitle><TableSkeleton rows={9} /></div>
  }

  if (!startSitData) {
    return <div><PageTitle>Start / Sit</PageTitle><p className="text-subtle">No recommendation available yet. Load your roster on the Dashboard first.</p></div>
  }

  const { week, season, season_type, starters = [], bench = [], close_decisions = [], offseason_note, warning } = startSitData
  const sortedStarters = [...starters].sort((a, b) => (SLOT_ORDER[a.slot] ?? 9) - (SLOT_ORDER[b.slot] ?? 9))
  const totalProj = sortedStarters.reduce((s, p) => s + (p.adjusted_proj || 0), 0)

  return (
    <div>
      <div className={`flex items-baseline justify-between mb-4 pb-4 border-b border-line ${REVEAL}`}>
        <h1 className="text-2xl font-display font-bold text-content">Start / Sit</h1>
        <span className="text-sm text-subtle font-mono">
          {season_type === 'off' ? `${season} Offseason` : `Week ${week} · ${season}`}
        </span>
      </div>

      {offseason_note && (
        <div className="p-4 bg-surface border border-line rounded-lg text-subtle text-sm">{offseason_note}</div>
      )}

      {warning && (
        <div className="mb-4 p-3 bg-warn/10 border border-warn/30 rounded-lg text-warn text-sm">{warning}</div>
      )}

      {!offseason_note && (
        <div className="flex gap-6 items-start">
          <div className={`flex-1 min-w-0 ${REVEAL}`} style={{ animationDelay: '90ms' }}>
            <div className="flex items-center justify-between mb-3">
              <h2 className={H2}>Recommended Lineup</h2>
              {totalProj > 0 && (
                <span className="font-mono tabular-nums text-bull text-base font-bold">{totalProj.toFixed(1)} <span className="text-subtle/60 text-xs uppercase">pts</span></span>
              )}
            </div>
            <div className="overflow-x-auto rounded-xl border border-line bg-surface">
              <table className="w-full text-left">
                <thead className="bg-raised border-b border-line">
                  <tr>
                    <th className="px-3 py-2.5 text-[11px] font-semibold text-subtle uppercase tracking-wider">Slot</th>
                    <th className="px-3 py-2.5 text-[11px] font-semibold text-subtle uppercase tracking-wider">Player</th>
                    <th className="px-3 py-2.5 text-right text-[11px] font-semibold text-content uppercase tracking-wider">Proj</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line/40">
                  {sortedStarters.length > 0
                    ? sortedStarters.map(p => <LineupRow key={`${p.slot}-${p.player_id}`} p={p} />)
                    : <tr><td colSpan={3} className="px-3 py-6 text-center text-subtle/60 text-sm">No starters could be set. Refresh projections on the Dashboard.</td></tr>
                  }
                </tbody>
              </table>
            </div>

            {bench.length > 0 && (
              <div className="mt-6">
                <h2 className={`${H2} mb-3`}>Bench</h2>
                <div className="overflow-x-auto rounded-xl border border-line bg-surface">
                  <table className="w-full text-left">
                    <tbody className="divide-y divide-line/40">
                      {bench.map(p => (
                        <tr key={p.player_id} className="hover:bg-raised/50 transition-colors">
                          <td className="px-3 py-2">
                            <div className="flex items-center gap-2.5">
                              <PlayerAvatar playerId={p.player_id} name={p.name} size="sm" />
                              <div className="min-w-0">
                                <div className="flex items-center gap-2">
                                  <span className="text-content">{p.name}</span>
                                  <InjuryBadge status={p.injury_status} />
                                </div>
                                <div className="text-xs text-subtle font-mono mt-0.5">{p.position} · {p.nfl_team}</div>
                              </div>
                            </div>
                          </td>
                          <td className="px-3 py-2 text-right font-mono tabular-nums text-sm font-medium">
                            <span className={projColor(p.adjusted_proj)}>
                              {p.adjusted_proj != null ? p.adjusted_proj.toFixed(1) : '-'}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>

          <div className={`w-72 shrink-0 ${REVEAL}`} style={{ animationDelay: '180ms' }}>
            <h2 className={`${H2} mb-3`}>Close Calls</h2>
            {close_decisions.length > 0 ? (
              <div className="flex flex-col gap-3">
                {close_decisions.map((d, i) => <CloseDecision key={`${d.slot}-${i}`} d={d} />)}
              </div>
            ) : (
              <p className="text-xs text-subtle/70">No close calls this week. Every slot has a clear starter.</p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
