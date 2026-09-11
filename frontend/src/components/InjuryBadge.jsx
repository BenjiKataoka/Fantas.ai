const STATUS_STYLES = {
  Questionable: 'bg-yellow-900/60 text-yellow-300 border border-yellow-700/40',
  Doubtful:     'bg-orange-900/60 text-orange-300 border border-orange-700/40',
  Out:          'bg-red-900/60 text-red-400 border border-red-700/40',
  IR:           'bg-red-900/60 text-red-400 border border-red-700/40',
}

const STATUS_LABEL = {
  Questionable: 'Q',
  Doubtful: 'D',
  Out: 'Out',
  IR: 'IR',
}

export default function InjuryBadge({ status }) {
  const style = STATUS_STYLES[status]
  if (!style) return null // Active — show nothing
  return (
    <span className={`text-xs font-semibold px-1.5 py-0.5 rounded ${style}`}>
      {STATUS_LABEL[status]}
    </span>
  )
}
