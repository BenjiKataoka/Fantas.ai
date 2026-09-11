/**
 * SentimentGauge — visual bar for sentiment_score (-1.0 to 1.0).
 * Left = negative (red), center = neutral, right = positive (green).
 *
 * Props:
 *   score  — float -1.0 to 1.0
 *   label  — sentiment_label string (e.g. "OPTIMISTIC", "PESSIMISTIC")
 */
export default function SentimentGauge({ score, label }) {
  if (score == null) return null

  // Map [-1, 1] → [0, 100]%
  const pct = ((score + 1) / 2) * 100

  const color  = score > 0.2 ? 'bg-green-500' : score < -0.2 ? 'bg-red-500' : 'bg-gray-500'
  const tColor = score > 0.2 ? 'text-green-400' : score < -0.2 ? 'text-red-400' : 'text-gray-400'

  return (
    <div className="flex flex-col gap-1">
      <div className="flex justify-between items-center">
        <span className="text-xs text-gray-500">Sentiment</span>
        <span className={`text-xs font-semibold ${tColor}`}>
          {label ?? (score > 0.2 ? 'OPTIMISTIC' : score < -0.2 ? 'PESSIMISTIC' : 'NEUTRAL')}
          <span className="font-mono ml-1 opacity-60">{score > 0 ? '+' : ''}{score.toFixed(2)}</span>
        </span>
      </div>
      {/* Track with center marker */}
      <div className="relative h-1.5 bg-gray-800 rounded-full overflow-hidden">
        {/* Center tick */}
        <div className="absolute left-1/2 top-0 bottom-0 w-px bg-gray-600" />
        {/* Filled segment from center to score */}
        {score >= 0 ? (
          <div
            className={`absolute top-0 bottom-0 rounded-full ${color}`}
            style={{ left: '50%', width: `${pct - 50}%` }}
          />
        ) : (
          <div
            className={`absolute top-0 bottom-0 rounded-full ${color}`}
            style={{ left: `${pct}%`, width: `${50 - pct}%` }}
          />
        )}
      </div>
    </div>
  )
}
