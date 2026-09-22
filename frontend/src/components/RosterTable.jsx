import { ChevronRight, TriangleAlert } from 'lucide-react'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'
import { useState } from 'react'
import InjuryBadge from './InjuryBadge'
import ProjectionBar from './ProjectionBar'
import ConfidenceBadge from './ConfidenceBadge'
import PlayerAvatar from './PlayerAvatar'
import StockSection from './StockSection'
import CollapseRow from './CollapseRow'
import { slotLabel } from '@/lib/utils'

// Concern is 1-10 from the AI analysis. 8+ is rare (2 of 15 on a typical roster), so the
// icon stays meaningful instead of decorating everyone.
const HIGH_CONCERN = 8

export function ConcernFlag({ stock }) {
  if (!stock || (stock.concern_level ?? 0) < HIGH_CONCERN) return null
  const reasons = (stock.bearish_factors || []).slice(0, 2)
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span tabIndex={0} aria-label={`High concern, ${stock.concern_level} out of 10`}
              className="ml-auto shrink-0 rounded p-1 text-bear hover:bg-bear/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-bear/40">
          <TriangleAlert className="size-4" />
        </span>
      </TooltipTrigger>
      <TooltipContent side="right" className="max-w-64">
        <p className="font-medium">High concern, {stock.concern_level}/10</p>
        {reasons.length ? (
          <ul className="mt-1 space-y-0.5 list-disc pl-4">{reasons.map(r => <li key={r}>{r}</li>)}</ul>
        ) : (
          stock.concern_summary && <p className="mt-1">{stock.concern_summary}</p>
        )}
      </TooltipContent>
    </Tooltip>
  )
}

// Position tints chosen to stay clear of the bull-green / bear-red market colors.
const POS_COLORS = {
  QB: 'text-pos-qb',
  RB: 'text-pos-rb',
  WR: 'text-pos-wr',
  TE: 'text-pos-te',
  K:  'text-subtle',
}

const COL_HEADER = 'px-3 py-2.5 text-left text-xs font-medium text-subtle'
const COL_CELL   = 'px-3 py-2.5 text-sm'

function SectionHeader({ label, count }) {
  return (
    <tr>
      <td colSpan={9} className="px-3 py-2 bg-raised text-xs font-display font-semibold text-subtle border-y border-line">
        {label} <span className="font-mono font-normal text-subtle/60 ml-1">({count})</span>
      </td>
    </tr>
  )
}

function StartSitCell({ rec }) {
  if (!rec) return <span className="text-subtle/40 text-xs">-</span>
  if (rec.slot) {
    return (
      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-bull/10 border border-bull/30 text-bull text-xs font-semibold">
        START<span className="text-bull/70 font-mono font-normal">{slotLabel(rec.slot)}</span>
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
          <ChevronRight className={`size-3.5 shrink-0 text-subtle/50 transition-transform ${isOpen ? 'rotate-90 text-brand' : ''}`} />
          <PlayerAvatar playerId={player_id} name={name} size="md" />
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-medium text-content">{name}</span>
              <InjuryBadge status={injury_status} />
            </div>
            <div className="text-xs text-subtle font-mono mt-0.5">{nfl_team}</div>
          </div>
          <ConcernFlag stock={stock} />
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

      {/* Weighted, the hero column */}
      <td className={`${COL_CELL} text-center bg-ink/40`}>
        <ProjectionBar value={weighted_proj} injuryStatus={injury_status} strong />
      </td>

      {/* Confidence */}
      <td className={`${COL_CELL} text-center`}><ConfidenceBadge flag={confidence_flag} /></td>

      {/* Latest News */}
      <td className={`${COL_CELL} max-w-[180px]`}>
        {latestNews ? (
          <p className="text-xs text-subtle leading-snug line-clamp-2">{latestNews.headline}</p>
        ) : (
          <span className="text-subtle/40 text-xs">-</span>
        )}
      </td>

      {/* Start/Sit */}
      <td className={`${COL_CELL} whitespace-nowrap`}><StartSitCell rec={startSitRec} /></td>
    </tr>
    {/* Drops open and collapses back up; column widths stay locked by table-fixed. */}
    <CollapseRow open={isOpen} colSpan={9}>
      <StockSection stock={stock} />
    </CollapseRow>
    </>
  )
}

/**
 * newsMap: { player_id: most-recent news card } from AppContext
 * startSitMap: { player_id: { slot } } for recommended starters; absent = SIT
 */
export default function RosterTable({ players, newsMap = {}, startSitMap = {} }) {
  const [openId, setOpenId] = useState(null)
  const toggle = (id) => setOpenId(prev => (prev === id ? null : id))
  const starters = players.filter(p => p.is_starter)
  const bench    = players.filter(p => !p.is_starter)

  return (
    <div className="rounded-xl border border-line bg-surface">
      {/* table-fixed + colgroup lock column widths (so the expandable row never reflows
          the table) AND size the table to exactly fit its container, no horizontal
          scroll, so opening a card never lets you swipe past the left/right edges.
          (A dedicated mobile pass comes after deploy.) */}
      <table className="w-full table-fixed text-left">
        <colgroup>
          <col className="w-[21%]" /> {/* Player */}
          <col className="w-[6%]" />  {/* Pos */}
          <col className="w-[9%]" />  {/* Slp */}
          <col className="w-[9%]" />  {/* ESPN */}
          <col className="w-[9%]" />  {/* FP */}
          <col className="w-[10%]" /> {/* Proj */}
          <col className="w-[8%]" />  {/* Conf */}
          <col className="w-[14%]" /> {/* News */}
          <col className="w-[14%]" /> {/* Start/Sit */}
        </colgroup>
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
