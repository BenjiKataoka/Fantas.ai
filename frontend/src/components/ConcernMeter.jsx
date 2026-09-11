/**
 * ConcernMeter — visual 1-10 bar for concern_level.
 * Green ≤3 · Yellow 4-6 · Red ≥7
 */
export default function ConcernMeter({ score }) {
  if (score == null) return null
  const pct = (score / 10) * 100
  const color = score <= 3 ? 'bg-green-500' : score <= 6 ? 'bg-yellow-500' : 'bg-red-500'
  const textColor = score <= 3 ? 'text-green-400' : score <= 6 ? 'text-yellow-400' : 'text-red-400'

  return (
    <div className="flex flex-col gap-1">
      <div className="flex justify-between items-center">
        <span className="text-xs text-gray-500">Concern</span>
        <span className={`text-xs font-semibold font-mono ${textColor}`}>{score}/10</span>
      </div>
      <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}
