import StockBadge from './StockBadge'

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

/**
 * AlertFeed — compact news sidebar for Dashboard.
 * Shows the most recent news items (up to maxItems) for rostered players.
 *
 * Props:
 *   items     — array of news cards from AppContext newsData.news
 *   playerMap — { player_id: { name, position } } built from rosterData
 *   maxItems  — max items to display (default 8)
 */
export default function AlertFeed({ items = [], playerMap = {}, maxItems = 8 }) {
  const visible = items
    .filter(item => item.stock_direction || item.analysis_tier === 'full')
    .slice(0, maxItems)

  if (!visible.length) {
    return (
      <p className="text-xs text-gray-600">No recent news for your roster.</p>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      {visible.map(item => {
        const player = playerMap[item.player_id]
        const label  = player ? `${player.name} · ${player.position}` : `Player ${item.player_id}`
        return (
          <div key={item.news_id} className="flex flex-col gap-1 py-2 border-b border-gray-800/60 last:border-0">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-medium text-gray-300 truncate">{label}</span>
              <span className="text-xs text-gray-600 shrink-0">{relativeTime(item.published_at)}</span>
            </div>
            <p className="text-xs text-gray-500 leading-snug line-clamp-2">{item.headline}</p>
            {item.stock_direction && (
              <StockBadge direction={item.stock_direction} magnitude={item.stock_magnitude} size="sm" />
            )}
          </div>
        )
      })}
    </div>
  )
}
