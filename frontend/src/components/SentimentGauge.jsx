/**
 * SentimentGauge — bar for sentiment_score (-1.0 to 1.0). Left negative, right positive.
 */
export default function SentimentGauge({ score, label }) {
  if (score == null) return null

  const pct = ((score + 1) / 2) * 100 // [-1,1] → [0,100]%
  const bar  = score > 0.2 ? 'bg-bull' : score < -0.2 ? 'bg-bear' : 'bg-subtle'
  const text = score > 0.2 ? 'text-bull' : score < -0.2 ? 'text-bear' : 'text-subtle'

  return (
    <div className="flex flex-col gap-1">
      <div className="flex justify-between items-center">
        <span className="text-xs text-subtle uppercase tracking-wide">Sentiment</span>
        <span className={`text-xs font-semibold ${text}`}>
          {label ?? (score > 0.2 ? 'OPTIMISTIC' : score < -0.2 ? 'PESSIMISTIC' : 'NEUTRAL')}
          <span className="font-mono tabular-nums ml-1 opacity-60">{score > 0 ? '+' : ''}{score.toFixed(2)}</span>
        </span>
      </div>
      <div className="relative h-1.5 bg-raised rounded-full overflow-hidden">
        <div className="absolute left-1/2 top-0 bottom-0 w-px bg-line" />
        {score >= 0 ? (
          <div className={`absolute top-0 bottom-0 rounded-full ${bar}`} style={{ left: '50%', width: `${pct - 50}%` }} />
        ) : (
          <div className={`absolute top-0 bottom-0 rounded-full ${bar}`} style={{ left: `${pct}%`, width: `${50 - pct}%` }} />
        )}
      </div>
    </div>
  )
}
