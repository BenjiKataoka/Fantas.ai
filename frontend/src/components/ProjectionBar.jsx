function projColor(value, injuryStatus) {
  if (injuryStatus === 'Out' || injuryStatus === 'IR') return 'text-bear'
  if (value == null) return 'text-subtle/40'
  if (value >= 15) return 'text-bull'
  if (value >= 8)  return 'text-warn'
  return 'text-bear'
}

export default function ProjectionBar({ value, injuryStatus, strong = false }) {
  if (value == null) return <span className="font-mono text-sm text-subtle/40">-</span>
  return (
    <span className={`font-mono tabular-nums ${strong ? 'text-base font-bold' : 'text-sm font-medium'} ${projColor(value, injuryStatus)}`}>
      {value.toFixed(1)}
    </span>
  )
}
