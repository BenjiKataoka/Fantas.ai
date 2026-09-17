export default function WeightSlider({ label, value, onChange }) {
  const pct = Math.round(value * 100)
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex justify-between items-center">
        <span className="text-sm text-subtle">{label}</span>
        <span className="font-mono text-sm text-content w-10 text-right tabular-nums">{pct}%</span>
      </div>
      <input
        type="range"
        min={0}
        max={100}
        value={pct}
        onChange={e => onChange(parseInt(e.target.value) / 100)}
        className="w-full h-1.5 accent-brand cursor-pointer"
      />
    </div>
  )
}
