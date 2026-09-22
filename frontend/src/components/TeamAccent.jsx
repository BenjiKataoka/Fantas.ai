import { teamAccent, teamName } from '@/lib/teams'
import { useTheme } from '@/lib/theme'

/**
 * A thin bar in the player's real NFL team color, left of his avatar. It gives the tables
 * some life and makes players from the same team easy to spot at a glance.
 */
export default function TeamAccent({ team }) {
  const dark = useTheme() === 'dark'
  const color = teamAccent(team, dark)
  if (!color) return <span className="w-0.5 shrink-0" aria-hidden />
  return <span className="w-0.5 h-7 shrink-0 rounded-full" style={{ background: color }} title={teamName(team)} aria-hidden />
}
