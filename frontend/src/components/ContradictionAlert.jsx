/**
 * ContradictionAlert — shown on full analysis cards when contradictions_flagged=true.
 * Displays the contradiction_detail text from Gemini Pass 2.
 */
export default function ContradictionAlert({ detail }) {
  if (!detail) return null
  return (
    <div className="flex items-start gap-2.5 p-3 bg-yellow-900/20 border border-yellow-800/50 rounded-lg">
      <span className="text-yellow-500 text-sm mt-0.5 shrink-0">⚠</span>
      <div>
        <p className="text-xs font-semibold text-yellow-400 mb-0.5">Contradiction Detected</p>
        <p className="text-xs text-yellow-300/80">{detail}</p>
      </div>
    </div>
  )
}
