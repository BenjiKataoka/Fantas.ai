import InjuryBadge from './InjuryBadge'
import ProjectionBar from './ProjectionBar'
import ConfidenceBadge from './ConfidenceBadge'
import StockBadge from './StockBadge'
import PlayerAvatar from './PlayerAvatar'

const POS_COLORS = {
  QB: 'text-red-400',
  RB: 'text-green-400',
  WR: 'text-blue-400',
  TE: 'text-yellow-400',
  K:  'text-gray-400',
}

const COL_HEADER = 'px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider'
const COL_CELL   = 'px-3 py-2.5 text-sm'

function SectionHeader({ label, count }) {
  return (
    <tr>
      <td colSpan={9} className="px-3 py-1.5 bg-gray-900/60 text-xs font-semibold text-gray-500 uppercase tracking-wider border-b border-gray-800">
        {label} <span className="font-normal text-gray-600 ml-1">({count})</span>
      </td>
    </tr>
  )
}

function StartSitCell({ rec }) {
  if (!rec) return <span className="text-gray-700 text-xs">—</span>
  if (rec.slot) {
    return (
      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-green-900/40 border border-green-800/50 text-green-400 text-xs font-semibold">
        START
        <span className="text-green-500/70 font-normal">{rec.slot}</span>
      </span>
    )
  }
  return (
    <span className="px-1.5 py-0.5 rounded bg-gray-800 border border-gray-700 text-gray-500 text-xs font-medium">
      SIT
    </span>
  )
}

function PlayerRow({ player, latestNews, startSitRec }) {
  const { player_id, name, position, nfl_team, injury_status, sleeper_proj, espn_proj, fp_proj, weighted_proj, confidence_flag } = player
  return (
    <tr className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors">
      {/* Player */}
      <td className={COL_CELL}>
        <div className="flex items-center gap-2.5">
          <PlayerAvatar playerId={player_id} name={name} size="md" />
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-medium text-white">{name}</span>
              <InjuryBadge status={injury_status} />
            </div>
            <div className="text-xs text-gray-500 mt-0.5">{nfl_team}</div>
          </div>
        </div>
      </td>

      {/* Pos */}
      <td className={COL_CELL}>
        <span className={`font-semibold text-xs ${POS_COLORS[position] || 'text-gray-400'}`}>
          {position}
        </span>
      </td>

      {/* Sleeper */}
      <td className={`${COL_CELL} text-center`}>
        <ProjectionBar value={sleeper_proj} injuryStatus={injury_status} />
      </td>

      {/* ESPN */}
      <td className={`${COL_CELL} text-center`}>
        <ProjectionBar value={espn_proj} injuryStatus={injury_status} />
      </td>

      {/* FP */}
      <td className={`${COL_CELL} text-center`}>
        <ProjectionBar value={fp_proj} injuryStatus={injury_status} />
      </td>

      {/* Weighted */}
      <td className={`${COL_CELL} text-center`}>
        <ProjectionBar value={weighted_proj} injuryStatus={injury_status} />
      </td>

      {/* Confidence */}
      <td className={`${COL_CELL} text-center`}>
        <ConfidenceBadge flag={confidence_flag} />
      </td>

      {/* Latest News */}
      <td className={`${COL_CELL} max-w-[180px]`}>
        {latestNews ? (
          <div className="flex flex-col gap-1">
            <p className="text-xs text-gray-400 leading-snug line-clamp-2">{latestNews.headline}</p>
            {latestNews.stock_direction && (
              <StockBadge direction={latestNews.stock_direction} magnitude={latestNews.stock_magnitude} size="sm" />
            )}
          </div>
        ) : (
          <span className="text-gray-700 text-xs">—</span>
        )}
      </td>

      {/* Start/Sit */}
      <td className={COL_CELL}>
        <StartSitCell rec={startSitRec} />
      </td>
    </tr>
  )
}

/**
 * newsMap     — { player_id: most-recent news card } — passed from Dashboard via AppContext
 * startSitMap — { player_id: { slot } } for recommended starters; players absent = SIT
 */
export default function RosterTable({ players, newsMap = {}, startSitMap = {} }) {
  const starters = players.filter(p => p.is_starter)
  const bench    = players.filter(p => !p.is_starter)

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-800">
      <table className="w-full text-left">
        <thead className="bg-gray-900 border-b border-gray-800">
          <tr>
            <th className={COL_HEADER}>Player</th>
            <th className={COL_HEADER}>Pos</th>
            <th className={`${COL_HEADER} text-center`}>Sleeper</th>
            <th className={`${COL_HEADER} text-center`}>ESPN</th>
            <th className={`${COL_HEADER} text-center`}>FP</th>
            <th className={`${COL_HEADER} text-center`}>Weighted</th>
            <th className={`${COL_HEADER} text-center`}>Conf</th>
            <th className={COL_HEADER}>News</th>
            <th className={COL_HEADER}>Start/Sit</th>
          </tr>
        </thead>
        <tbody className="bg-gray-950 divide-y divide-gray-800/30">
          {starters.length > 0 && (
            <>
              <SectionHeader label="Starters" count={starters.length} />
              {starters.map(p => <PlayerRow key={p.player_id} player={p} latestNews={newsMap[p.player_id]} startSitRec={startSitMap[p.player_id]} />)}
            </>
          )}
          {bench.length > 0 && (
            <>
              <SectionHeader label="Bench" count={bench.length} />
              {bench.map(p => <PlayerRow key={p.player_id} player={p} latestNews={newsMap[p.player_id]} startSitRec={startSitMap[p.player_id]} />)}
            </>
          )}
        </tbody>
      </table>
    </div>
  )
}
