const STATUS_STYLES = {
  Questionable: 'bg-warn/15 text-warn border border-warn/30',
  Doubtful:     'bg-warn/20 text-warn border border-warn/40',
  Out:          'bg-bear/15 text-bear border border-bear/30',
  IR:           'bg-bear/15 text-bear border border-bear/30',
}

const STATUS_LABEL = { Questionable: 'Q', Doubtful: 'D', Out: 'Out', IR: 'IR' }

export default function InjuryBadge({ status }) {
  const style = STATUS_STYLES[status]
  if (!style) return null // Active, show nothing
  return (
    <span className={`text-xs font-semibold px-1.5 py-0.5 rounded ${style}`}>
      {STATUS_LABEL[status]}
    </span>
  )
}
