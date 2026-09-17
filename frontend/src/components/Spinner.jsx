export default function Spinner({ label = 'Loading…' }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-subtle">
      <div className="w-8 h-8 border-2 border-line border-t-brand rounded-full animate-spin" />
      <span className="text-sm">{label}</span>
    </div>
  )
}
