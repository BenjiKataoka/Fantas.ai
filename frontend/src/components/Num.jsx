// Shared numeric cell: monospaced and tabular so columns line up.
export default function Num({ children, className = '' }) {
  return <span className={`font-mono tabular-nums ${className}`}>{children}</span>
}
