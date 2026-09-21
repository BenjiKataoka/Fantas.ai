import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'

const STYLES = {
  HIGH:   'text-bull',
  MEDIUM: 'text-warn',
  LOW:    'text-bear',
}

const EXPLAIN = {
  HIGH:   'All 3 projection sources contributed',
  MEDIUM: '2 of 3 sources contributed',
  LOW:    'Only 1 source available. Treat with caution.',
}

export default function ConfidenceBadge({ flag }) {
  if (!flag) return null
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className={`text-xs font-medium cursor-help ${STYLES[flag] || 'text-subtle'}`}>
          {flag}
        </span>
      </TooltipTrigger>
      <TooltipContent>{EXPLAIN[flag] || 'Projection source confidence'}</TooltipContent>
    </Tooltip>
  )
}
