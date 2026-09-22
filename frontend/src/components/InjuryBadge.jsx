const STATUS_STYLES = {
  Questionable: 'bg-warn/15 text-warn border border-warn/30',
  Doubtful:     'bg-warn/20 text-warn border border-warn/40',
  Out:          'bg-bear/15 text-bear border border-bear/30',
  IR:           'bg-bear/15 text-bear border border-bear/30',
}

import { Hint } from '@/components/ui/tooltip'

const STATUS_LABEL = { Questionable: 'Q', Doubtful: 'D', Out: 'Out', IR: 'IR' }
const STATUS_HINT = {
  Questionable: 'Questionable: might not play. Check his status before kickoff.',
  Doubtful:     'Doubtful: unlikely to play this week.',
  Out:          'Out: ruled out for this week. Projects zero.',
  IR:           'Injured reserve: out for at least four weeks.',
}

export default function InjuryBadge({ status }) {
  const style = STATUS_STYLES[status]
  if (!style) return null // Active, show nothing
  return (
    <Hint text={STATUS_HINT[status]}>
      <span className={`text-xs font-semibold px-1.5 py-0.5 rounded ${style}`}>
        {STATUS_LABEL[status]}
      </span>
    </Hint>
  )
}
