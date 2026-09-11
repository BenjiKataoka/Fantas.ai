function projColor(value, injuryStatus) {
  if (injuryStatus === 'Out' || injuryStatus === 'IR') return 'text-red-400'
  if (value == null) return 'text-gray-600'
  if (value >= 15) return 'text-green-400'
  if (value >= 8)  return 'text-yellow-400'
  return 'text-red-400'
}

export default function ProjectionBar({ value, injuryStatus }) {
  if (value == null) return <span className="text-gray-600">—</span>
  return (
    <span className={`font-mono text-sm font-medium ${projColor(value, injuryStatus)}`}>
      {value.toFixed(1)}
    </span>
  )
}
