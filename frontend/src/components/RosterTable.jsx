import { useState } from 'react'
import InjuryBadge from './InjuryBadge'
import ProjectionBar from './ProjectionBar'
import ConfidenceBadge from './ConfidenceBadge'
import StockBadge from './StockBadge'
import PlayerAvatar from './PlayerAvatar'
import StockSection from './StockSection'

// Small dot summarizing a player's concern level on the collapsed row (green/amber/red).
function ConcernDot({ level }) {
  if (level == null) return null
  const c = level <= 3 ? 'bg-bull' : level <= 6 ? 'bg-warn' : 'bg-bear'
  return <span className={`h-1.5 w-1.5 rounded-full ${c}`} title={`Concern ${level}/10`} />
}

// Position tints chosen to stay clear of the bull-green / bear-red market colors.
const POS_COLORS = {
  QB: 'text-violet-300',
  RB: 'text-teal-300',
  WR: 'text-sky-300',
  TE: 'text-amber-300',
  K:  'text-subtle',
}

const COL_HEADER = 'px-3 py-2.5 text-left text-[11px] font-semibold text-subtle uppercase tracking-wider'
const COL_CELL   = 'px-3 py-2.5 text-sm'

function SectionHeader({ label, count }) {
  return (
    <tr>
      <td colSpan={9} className="px-3 py-2 bg-raised text-[11px] font-display font-semibold text-subtle uppercase tracking-widest border-y border-line">
        {label} <span className="font-mono font-normal text-subtle/60 ml-1">({count})</span>
      </td>
    </tr>
  )
}

function StartSitCell({ rec }) {
  if (!rec) return <span className="text-subtle/40 text-xs">—</span>
  if (rec.slot) {
    return (
      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-bull/10 border border-bull/30 text-bull text-xs font-semibold">
        START<span className="text-bull/70 font-mono font-normal">{rec.slot}</span>
      </span>
    )
  }
  return (
    <span className="px-1.5 py-0.5 rounded bg-raised border border-line text-subtle text-xs font-medium">
      SIT
    </span>
  )
}

function PlayerRow({ player, latestNews, startSitRec, isOpen, onToggle }) {
  const { player_id, name, position, nfl_team, injury_status, sleeper_proj, espn_proj, fp_proj, weighted_proj, confidence_flag, stock } = player
  return (
    <>
    <tr
      className="hover:bg-raised/50 transition-colors cursor-pointer"
      onClick={onToggle}
      aria-expanded={isOpen}
    >
      {/* Player */}
      <td className={COL_CELL}>
        <div className="flex items-center gap-2.5">
          <span className={`text-subtle/50 text-xs transition-transform ${isOpen ? 'rotate-90 text-brand' : ''}`}>▸</span>
          <PlayerAvatar playerId={player_id} name={name} size="md" />
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-medium text-content">{name}</span>
              <InjuryBadge status={injury_status} />
              {stock && <ConcernDot level={stock.concern_level} />}
            </div>
            <div className="text-xs text-subtle font-mono mt-0.5">{nfl_team}</div>
          </div>
        </div>
      </td>

      {/* Pos */}
      <td className={COL_CELL}>
        <span className={`font-mono font-semibold text-xs ${POS_COLORS[position] || 'text-subtle'}`}>
          {position}
        </span>
      </td>

      {/* Source projections */}
      <td className={`${COL_CELL} text-center`}><ProjectionBar value={sleeper_proj} injuryStatus={injury_status} /></td>
      <td className={`${COL_CELL} text-center`}><ProjectionBar value={espn_proj} injuryStatus={injury_status} /></td>
      <td className={`${COL_CELL} text-center`}><ProjectionBar value={fp_proj} injuryStatus={injury_status} /></td>

      {/* Weighted — the hero column */}
      <td className={`${COL_CELL} text-center bg-ink/40`}>
        <ProjectionBar value={weighted_proj} injuryStatus={injury_status} strong />
      </td>

      {/* Confidence */}
      <td className={`${COL_CELL} text-center`}><ConfidenceBadge flag={confidence_flag} /></td>

      {/* Latest News */}
      <td className={`${COL_CELL} max-w-[180px]`}>
        {latestNews ? (
          <div className="flex flex-col gap-1">
            <p className="text-xs text-subtle leading-snug line-clamp-2">{latestNews.headline}</p>
            {latestNews.stock_direction && (
              <StockBadge direction={latestNews.stock_direction} magnitude={latestNews.stock_magnitude} size="sm" />
            )}
          </div>
        ) : (
          <span className="text-subtle/40 text-xs">—</span>
        )}
      </td>

      {/* Start/Sit */}
      <td className={COL_CELL}><StartSitCell rec={startSitRec} /></td>
    </tr>
    {isOpen && (
      <tr>
        <td colSpan={9} className="p-0 bg-ink/30 border-l-2 border-brand">
          <StockSection stock={stock} />
        </td>
      </tr>
    )}
    </>
  )
}

/**
 * newsMap     — { player_id: most-recent news card } from AppContext
 * startSitMap — { player_id: { slot } } for recommended starters; absent = SIT
 */
export default function RosterTable({ players, newsMap = {}, startSitMap = {} }) {
  const [openId, setOpenId] = useState(null)
  const toggle = (id) => setOpenId(prev => (prev === id ? null : id))
  const starters = players.filter(p => p.is_starter)
  const bench    = players.filter(p => !p.is_starter)

  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-surface">
      <table className="w-full text-left">
        <thead className="bg-raised border-b border-line">
          <tr>
            <th className={COL_HEADER}>Player</th>
            <th className={COL_HEADER}>Pos</th>
            <th className={`${COL_HEADER} text-center`}>Slp</th>
            <th className={`${COL_HEADER} text-center`}>ESPN</th>
            <th className={`${COL_HEADER} text-center`}>FP</th>
            <th className={`${COL_HEADER} text-center text-content`}>Proj</th>
            <th className={`${COL_HEADER} text-center`}>Conf</th>
            <th className={COL_HEADER}>News</th>
            <th className={COL_HEADER}>Start/Sit</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line/40">
          {starters.length > 0 && (
            <>
              <SectionHeader label="Starters" count={starters.length} />
              {starters.map(p => <PlayerRow key={p.player_id} player={p} latestNews={newsMap[p.player_id]} startSitRec={startSitMap[p.player_id]} isOpen={openId === p.player_id} onToggle={() => toggle(p.player_id)} />)}
            </>
          )}
          {bench.length > 0 && (
            <>
              <SectionHeader label="Bench" count={bench.length} />
              {bench.map(p => <PlayerRow key={p.player_id} player={p} latestNews={newsMap[p.player_id]} startSitRec={startSitMap[p.player_id]} isOpen={openId === p.player_id} onToggle={() => toggle(p.player_id)} />)}
            </>
          )}
        </tbody>
      </table>
    </div>
  )
}
