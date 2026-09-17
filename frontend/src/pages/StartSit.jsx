import { useApp } from '../context/AppContext'
import Spinner from '../components/Spinner'
import InjuryBadge from '../components/InjuryBadge'
import PlayerAvatar from '../components/PlayerAvatar'

// ── Helpers ─────────────────────────────────────────────────────────────────

const SLOT_ORDER = { QB: 0, RB: 1, WR: 2, TE: 3, FLEX: 4, K: 5 }

const SLOT_COLORS = {
  QB:   'text-red-400',
  RB:   'text-green-400',
  WR:   'text-blue-400',
  TE:   'text-yellow-400',
  FLEX: 'text-purple-400',
  K:    'text-gray-400',
}

function projColor(v) {
  if (v == null) return 'text-gray-600'
  if (v >= 15)   return 'text-green-400'
  if (v >= 8)    return 'text-yellow-400'
  return 'text-red-400'
}

// ── Sub-components ───────────────────────────────────────────────────────────

function LineupRow({ p }) {
  return (
    <tr className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors">
      <td className="px-3 py-2.5">
        <span className={`font-semibold text-xs uppercase tracking-wide ${SLOT_COLORS[p.slot] || 'text-gray-400'}`}>
          {p.slot}
        </span>
      </td>
      <td className="px-3 py-2.5">
        <div className="flex items-center gap-2.5">
          <PlayerAvatar playerId={p.player_id} name={p.name} size="md" />
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-medium text-white">{p.name}</span>
              <InjuryBadge status={p.injury_status} />
            </div>
            <div className="text-xs text-gray-500 mt-0.5">{p.position} · {p.nfl_team}</div>
          </div>
        </div>
      </td>
      <td className="px-3 py-2.5 text-right font-mono text-sm">
        <span className={projColor(p.adjusted_proj)}>
          {p.adjusted_proj != null ? p.adjusted_proj.toFixed(1) : '—'}
        </span>
      </td>
    </tr>
  )
}

function CloseDecision({ d }) {
  return (
    <div className="bg-amber-950/30 border border-amber-800/40 rounded-lg p-3">
      <div className="flex items-center gap-2 mb-2">
        <span className={`text-xs font-semibold uppercase ${SLOT_COLORS[d.slot] || 'text-gray-400'}`}>{d.slot}</span>
        <span className="text-xs text-amber-500/80 font-mono">margin {d.margin.toFixed(1)}</span>
      </div>
      <div className="flex items-center gap-2 text-sm">
        <span className="text-green-400 font-medium">{d.start.name}</span>
        <span className="text-gray-500 text-xs">{d.start.adjusted_proj?.toFixed(1)}</span>
        <span className="text-gray-600 mx-1">over</span>
        <span className="text-gray-400">{d.sit.name}</span>
        <span className="text-gray-600 text-xs">{d.sit.adjusted_proj?.toFixed(1)}</span>
      </div>
      <p className="text-xs text-amber-500/70 mt-1.5">{d.note}</p>
    </div>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function StartSit() {
  const { credentials, startSitData, startSitLoading } = useApp()

  if (!credentials) {
    return (
      <div>
        <h1 className="text-2xl font-bold mb-2">Start / Sit</h1>
        <p className="text-gray-400">Connect your league on the Dashboard to see lineup recommendations.</p>
      </div>
    )
  }

  if (startSitLoading && !startSitData) {
    return (
      <div>
        <h1 className="text-2xl font-bold mb-4">Start / Sit</h1>
        <Spinner label="Building lineup recommendation…" />
      </div>
    )
  }

  if (!startSitData) {
    return (
      <div>
        <h1 className="text-2xl font-bold mb-2">Start / Sit</h1>
        <p className="text-gray-400">No recommendation available yet. Load your roster on the Dashboard first.</p>
      </div>
    )
  }

  const { week, season, season_type, starters = [], bench = [], close_decisions = [], offseason_note, warning } = startSitData

  const sortedStarters = [...starters].sort((a, b) => (SLOT_ORDER[a.slot] ?? 9) - (SLOT_ORDER[b.slot] ?? 9))
  const totalProj = sortedStarters.reduce((s, p) => s + (p.adjusted_proj || 0), 0)

  return (
    <div>
      <div className="flex items-baseline justify-between mb-4 pb-4 border-b border-gray-800">
        <h1 className="text-2xl font-bold">Start / Sit</h1>
        <span className="text-sm text-gray-500">
          {season_type === 'off' ? `${season} Offseason` : `Week ${week} · ${season}`}
        </span>
      </div>

      {offseason_note && (
        <div className="p-4 bg-gray-900 border border-gray-800 rounded-lg text-gray-400 text-sm">
          {offseason_note}
        </div>
      )}

      {warning && (
        <div className="mb-4 p-3 bg-yellow-900/30 border border-yellow-800 rounded-lg text-yellow-400 text-sm">
          {warning}
        </div>
      )}

      {!offseason_note && (
        <div className="flex gap-6 items-start">
          {/* Recommended lineup */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">Recommended Lineup</h2>
              {totalProj > 0 && (
                <span className="text-sm font-mono text-green-400">{totalProj.toFixed(1)} pts</span>
              )}
            </div>
            <div className="overflow-x-auto rounded-lg border border-gray-800">
              <table className="w-full text-left">
                <thead className="bg-gray-900 border-b border-gray-800">
                  <tr>
                    <th className="px-3 py-2 text-xs font-semibold text-gray-500 uppercase tracking-wider">Slot</th>
                    <th className="px-3 py-2 text-xs font-semibold text-gray-500 uppercase tracking-wider">Player</th>
                    <th className="px-3 py-2 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">Proj</th>
                  </tr>
                </thead>
                <tbody className="bg-gray-950">
                  {sortedStarters.length > 0
                    ? sortedStarters.map(p => <LineupRow key={`${p.slot}-${p.player_id}`} p={p} />)
                    : <tr><td colSpan={3} className="px-3 py-6 text-center text-gray-600 text-sm">No starters could be set — sync projections on the Dashboard.</td></tr>
                  }
                </tbody>
              </table>
            </div>

            {/* Bench */}
            {bench.length > 0 && (
              <div className="mt-6">
                <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-3">Bench</h2>
                <div className="overflow-x-auto rounded-lg border border-gray-800">
                  <table className="w-full text-left">
                    <tbody className="bg-gray-950">
                      {bench.map(p => (
                        <tr key={p.player_id} className="border-b border-gray-800/50 last:border-0 hover:bg-gray-800/30 transition-colors">
                          <td className="px-3 py-2">
                            <div className="flex items-center gap-2.5">
                              <PlayerAvatar playerId={p.player_id} name={p.name} size="sm" />
                              <div className="min-w-0">
                                <div className="flex items-center gap-2">
                                  <span className="text-gray-300">{p.name}</span>
                                  <InjuryBadge status={p.injury_status} />
                                </div>
                                <div className="text-xs text-gray-600 mt-0.5">{p.position} · {p.nfl_team}</div>
                              </div>
                            </div>
                          </td>
                          <td className="px-3 py-2 text-right font-mono text-sm">
                            <span className={projColor(p.adjusted_proj)}>
                              {p.adjusted_proj != null ? p.adjusted_proj.toFixed(1) : '—'}
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

          {/* Close decisions sidebar */}
          <div className="w-72 shrink-0">
            <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-3">Close Calls</h2>
            {close_decisions.length > 0 ? (
              <div className="flex flex-col gap-3">
                {close_decisions.map((d, i) => <CloseDecision key={`${d.slot}-${i}`} d={d} />)}
              </div>
            ) : (
              <p className="text-xs text-gray-600">No close calls — every slot has a clear starter.</p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
