import PlayerAvatar from './PlayerAvatar'

function relativeTime(isoStr) {
  if (!isoStr) return ''
  const diff = Date.now() - new Date(isoStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1)  return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24)  return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

// What counts as "alert-worthy": actionable categories or a real directional signal.
// General/performance chatter is excluded here (it still shows in the News Hub).
const TYPE_SCORE = { INJURY: 3, TRANSACTION: 3, DEPTH_CHART: 2, CONTRACT: 2 }
const MAG_SCORE  = { HIGH: 3, MEDIUM: 2, LOW: 1 }
const SIGNAL     = new Set(['BULLISH', 'BEARISH'])

const TYPE_LABEL = {
  INJURY:      { text: 'Injury',      cls: 'text-bear' },
  TRANSACTION: { text: 'Transaction', cls: 'text-info' },
  DEPTH_CHART: { text: 'Depth',       cls: 'text-warn' },
  CONTRACT:    { text: 'Contract',    cls: 'text-brand' },
}

const isMeaningful = (i) => (TYPE_SCORE[i.news_type] || 0) >= 2 || SIGNAL.has(i.stock_direction)

// Higher = more important. Significant type dominates, then magnitude, then a bull/bear
// signal, then whether a full Gemini analysis exists.
function importance(i) {
  const t = (TYPE_SCORE[i.news_type] || 0) * 4
  const m = (MAG_SCORE[i.stock_magnitude] || 0) * 2
  const d = SIGNAL.has(i.stock_direction) ? 2 : 0
  const full = i.analysis_tier === 'full' ? 1 : 0
  return t + m + d + full
}

const recency = (i) => (i.published_at ? new Date(i.published_at).getTime() : 0)

/**
 * AlertFeed: a curated (not chronological) sidebar of the roster's meaningful news.
 * Filters to actionable items, keeps the single most-important alert per player, and
 * ranks by importance then recency so one player can't flood the feed.
 *
 * Props:
 *   items: news cards from AppContext newsData.news
 *   playerMap: { player_id: { name, position } } from rosterData
 *   maxItems: max alerts to display (default 6)
 *   lineups: optional { player_id: lineups he starts in } (portfolio) → "affects N lineups"
 */
export default function AlertFeed({ items = [], playerMap = {}, maxItems = 6, lineups = {} }) {
  // 1) keep only meaningful items, 2) best one per player, 3) rank, 4) cap.
  const bestPerPlayer = new Map()
  for (const item of items) {
    if (!isMeaningful(item)) continue
    const prev = bestPerPlayer.get(item.player_id)
    if (!prev || importance(item) > importance(prev) ||
        (importance(item) === importance(prev) && recency(item) > recency(prev))) {
      bestPerPlayer.set(item.player_id, item)
    }
  }

  const visible = [...bestPerPlayer.values()]
    .sort((a, b) => importance(b) - importance(a) || recency(b) - recency(a))
    .slice(0, maxItems)

  if (!visible.length) {
    return <p className="text-xs text-subtle/70">No injury or roster alerts right now.</p>
  }

  return (
    <div className="flex flex-col gap-2">
      {visible.map(item => {
        const player = playerMap[item.player_id] || (item.player_name && { name: item.player_name, position: item.position })
        const label  = player ? `${player.name} · ${player.position}` : 'Unknown player'
        const type   = TYPE_LABEL[item.news_type]
        return (
          <div key={item.news_id} className="flex gap-2 py-2 border-b border-line/60 last:border-0">
            <PlayerAvatar playerId={item.player_id} name={player?.name} size="sm" />
            <div className="flex flex-col gap-1 min-w-0 flex-1">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-medium text-content truncate">{label}</span>
                <span className="text-xs text-subtle/70 shrink-0 font-mono">{relativeTime(item.published_at)}</span>
              </div>
              <p className="text-xs text-subtle leading-snug line-clamp-2">{item.headline}</p>
              {(type || lineups[item.player_id] > 1) && (
                <span className="text-xs font-medium">
                  {type && <span className={type.cls}>{type.text}</span>}
                  {lineups[item.player_id] > 1 && <span className="text-content/80">{type ? ' · ' : ''}Affects {lineups[item.player_id]} lineups</span>}
                </span>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
