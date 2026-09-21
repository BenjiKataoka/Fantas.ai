const DIRECTION_STYLES = {
  BULLISH: { bg: 'bg-bull/10', text: 'text-bull',   border: 'border-bull/30' },
  BEARISH: { bg: 'bg-bear/10', text: 'text-bear',   border: 'border-bear/30' },
  NEUTRAL: { bg: 'bg-raised',  text: 'text-subtle', border: 'border-line'    },
}

/**
 * StockBadge: BULLISH/BEARISH/NEUTRAL direction + optional magnitude.
 * size: "sm" (table cells) | "md" (default).
 */
export default function StockBadge({ direction, magnitude, size = 'md' }) {
  if (!direction) return null
  const d = DIRECTION_STYLES[direction] ?? DIRECTION_STYLES.NEUTRAL
  const textSize = size === 'sm' ? 'text-xs' : 'text-sm'

  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded border ${d.bg} ${d.border}`}>
      <span className={`${textSize} font-semibold tracking-wide ${d.text}`}>{direction}</span>
      {magnitude && <span className={`text-xs font-mono ${d.text} opacity-70`}>{magnitude}</span>}
    </span>
  )
}
