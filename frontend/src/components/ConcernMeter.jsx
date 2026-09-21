/**
 * ConcernMeter: 1-10 bar for concern_level. Bull ≤3 · Warn 4-6 · Bear ≥7.
 */
export default function ConcernMeter({ score }) {
  if (score == null) return null
  const pct = (score / 10) * 100
  const bar  = score <= 3 ? 'bg-bull' : score <= 6 ? 'bg-warn' : 'bg-bear'
  const text = score <= 3 ? 'text-bull' : score <= 6 ? 'text-warn' : 'text-bear'

  return (
    <div className="flex flex-col gap-1">
      <div className="flex justify-between items-center">
        <span className="text-xs text-subtle uppercase tracking-wide">Concern</span>
        <span className={`text-xs font-semibold font-mono tabular-nums ${text}`}>{score}/10</span>
      </div>
      <div className="h-1.5 bg-raised rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${bar}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}
