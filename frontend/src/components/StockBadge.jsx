const DIRECTION_STYLES = {
  BULLISH: { bg: 'bg-green-900/40', text: 'text-green-400', border: 'border-green-800/50' },
  BEARISH: { bg: 'bg-red-900/40',   text: 'text-red-400',   border: 'border-red-800/50'   },
  NEUTRAL: { bg: 'bg-gray-800',     text: 'text-gray-400',  border: 'border-gray-700'     },
}

/**
 * StockBadge — shows BULLISH/BEARISH/NEUTRAL direction + optional magnitude label.
 *
 * Props:
 *   direction  — "BULLISH" | "BEARISH" | "NEUTRAL"
 *   magnitude  — "HIGH" | "MEDIUM" | "LOW" (optional)
 *   size       — "sm" (compact, for table cells) | "md" (default)
 */
export default function StockBadge({ direction, magnitude, size = 'md' }) {
  if (!direction) return null
  const d = DIRECTION_STYLES[direction] ?? DIRECTION_STYLES.NEUTRAL
  const textSize = size === 'sm' ? 'text-xs' : 'text-sm'

  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded border ${d.bg} ${d.border}`}>
      <span className={`${textSize} font-semibold ${d.text}`}>{direction}</span>
      {magnitude && (
        <span className={`text-xs ${d.text} opacity-70`}>{magnitude}</span>
      )}
    </span>
  )
}
