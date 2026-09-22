// Three bouncing dots (daisyUI-style). Inline next to text, or centered as a block.
export function LoadingDots({ className = '' }) {
  return (
    <span className={`loading-dots ${className}`} aria-hidden>
      <span /><span /><span />
    </span>
  )
}

export default function Spinner({ label = 'Loading' }) {
  return (
    <div role="status" className="flex flex-col items-center justify-center gap-3 py-16 text-subtle">
      <LoadingDots className="text-2xl text-content/70" />
      <span className="text-sm">{label}</span>
    </div>
  )
}
