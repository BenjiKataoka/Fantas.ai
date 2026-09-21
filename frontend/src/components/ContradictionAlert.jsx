import { TriangleAlert } from 'lucide-react'
/**
 * ContradictionAlert: shown on full analysis cards when contradictions_flagged=true.
 */
export default function ContradictionAlert({ detail }) {
  if (!detail) return null
  return (
    <div className="flex items-start gap-2.5 p-3 bg-warn/10 border border-warn/30 rounded-lg">
      <TriangleAlert className="size-4 text-warn mt-0.5 shrink-0" />
      <div>
        <p className="text-xs font-semibold text-warn mb-0.5">Contradiction detected</p>
        <p className="text-xs text-warn/80">{detail}</p>
      </div>
    </div>
  )
}
