import { useState } from 'react'

// Single-metric chart. Every metric is drawn so UP = BETTER, on a real axis labeled
// with actual values and auto-scaled to THIS player's range (so a WR3 and a WR9 each
// get a fitted axis). `betterHigh` flips the orientation; `domain:'auto'` fits the data.
// Metric line colors are fixed on purpose (each metric keeps its identity in both themes);
// the grid and labels follow the theme through CSS variables, applied via style props
// because SVG attributes don't resolve var().
export const METRICS = {
  rank: {
    label: 'Position Rank', color: '#7C5CFF', betterHigh: false, domain: 'auto',
    accessor: p => p.rank,
    value: (v, pos) => `${pos || ''}${Math.round(v)}`,   // "RB4"
    unit: 'spots',
  },
  sentiment: {
    label: 'Sentiment', color: '#38BDF8', betterHigh: true, domain: [-1, 1],
    accessor: p => p.sentiment,
    value: v => `${v > 0 ? '+' : ''}${v.toFixed(2)}`,
    unit: 'pts',
  },
  rostered: {
    label: '% Rostered', color: '#34D399', betterHigh: true, domain: 'auto',
    accessor: p => p.rostered,
    value: v => `${v.toFixed(1)}%`,
    unit: '%',
  },
  adp: {
    label: 'ADP', color: '#2DD4BF', betterHigh: false, domain: 'auto',
    accessor: p => p.adp,
    value: v => `${v.toFixed(1)}`,
    unit: 'picks',
  },
  concern: {
    label: 'Concern', color: '#FBBF24', betterHigh: false, domain: [1, 10],
    accessor: p => p.concern,
    value: v => `${Math.round(v)}/10`,
    unit: '',
  },
}

const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
const fmtDate = t => { const [, m, d] = t.split('-'); return `${MON[+m - 1]} ${+d}` }

export default function TrendChart({ points = [], metric = 'rank', position = '' }) {
  const [hover, setHover] = useState(null)
  const m = METRICS[metric]

  const vals = points.map((p, i) => ({ v: m.accessor(p), i, t: p.t })).filter(d => d.v != null)
  if (!vals.length) {
    return <div className="h-[210px] flex items-center justify-center text-sm text-subtle">No {m.label.toLowerCase()} data for this range yet.</div>
  }

  // Domain (auto-fit to the player, or fixed for bounded metrics), with padding.
  let [lo, hi] = m.domain === 'auto'
    ? [Math.min(...vals.map(d => d.v)), Math.max(...vals.map(d => d.v))]
    : m.domain
  if (lo === hi) { lo -= 1; hi += 1 }
  else if (m.domain === 'auto') { const pad = (hi - lo) * 0.18; lo -= pad; hi += pad }

  const W = 640, H = 210, padL = 44, padR = 14, padT = 14, padB = 24
  const innerW = W - padL - padR, innerH = H - padT - padB
  const n = points.length
  const xFor = i => (n <= 1 ? padL + innerW / 2 : padL + (i / (n - 1)) * innerW)
  const goodness = v => { const t = (v - lo) / (hi - lo); return m.betterHigh ? t : 1 - t } // 1 = best
  const yFor = v => padT + (1 - goodness(v)) * innerH

  const line = vals.map((d, k) => `${k === 0 ? 'M' : 'L'}${xFor(d.i).toFixed(1)},${yFor(d.v).toFixed(1)}`).join(' ')

  // Three axis ticks: best (top), middle, worst (bottom), labeled with real values.
  const bestV = m.betterHigh ? hi : lo
  const worstV = m.betterHigh ? lo : hi
  const ticks = [{ v: bestV, y: padT }, { v: (lo + hi) / 2, y: padT + innerH / 2 }, { v: worstV, y: padT + innerH }]

  const labelIdx = n <= 1 ? [0] : [0, Math.floor((n - 1) / 2), n - 1]
  const hoverX = hover != null ? xFor(hover) : 0

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full select-none" preserveAspectRatio="xMidYMid meet" onMouseLeave={() => setHover(null)}>
        <defs>
          <linearGradient id="goodbad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" style={{ stopColor: 'var(--bull)', stopOpacity: 0.10 }} />
            <stop offset="50%" style={{ stopColor: 'var(--bull)', stopOpacity: 0 }} />
            <stop offset="100%" style={{ stopColor: 'var(--bear)', stopOpacity: 0.10 }} />
          </linearGradient>
        </defs>

        {/* good/bad shading (up = good) */}
        <rect x={padL} y={padT} width={innerW} height={innerH} fill="url(#goodbad)" />

        {/* axis ticks + gridlines */}
        {ticks.map((tk, i) => (
          <g key={i}>
            <line x1={padL} x2={W - padR} y1={tk.y} y2={tk.y} style={{ stroke: 'var(--chart-grid)' }} />
            <text x={padL - 8} y={tk.y + 3} fontSize="10" style={{ fill: 'var(--chart-label)' }} textAnchor="end" fontFamily="monospace">
              {m.value(tk.v, position)}
            </text>
          </g>
        ))}

        {/* hover guide */}
        {hover != null && <line x1={hoverX} x2={hoverX} y1={padT} y2={H - padB} style={{ stroke: 'var(--chart-label)', strokeOpacity: 0.4 }} />}

        {/* the metric line */}
        <path d={line} fill="none" style={{ stroke: m.color }} strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
        {vals.map(d => <circle key={d.i} cx={xFor(d.i)} cy={yFor(d.v)} r={hover === d.i ? 4 : 2.4} style={{ fill: m.color }} />)}

        {/* x-axis date labels */}
        {labelIdx.map(i => (
          <text key={i} x={xFor(i)} y={H - 6} fontSize="10" style={{ fill: 'var(--chart-label)' }}
                textAnchor={i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'} fontFamily="monospace">
            {fmtDate(points[i].t)}
          </text>
        ))}

        {/* hover bands */}
        {points.map((p, i) => (
          <rect key={i} x={xFor(i) - innerW / (2 * Math.max(1, n - 1 || 1))} y={padT}
                width={innerW / Math.max(1, n - 1 || 1)} height={innerH}
                fill="transparent" onMouseEnter={() => setHover(i)} />
        ))}
      </svg>

      {hover != null && m.accessor(points[hover]) != null && (
        <div
          className="pointer-events-none absolute top-1 z-10 rounded-lg border border-line bg-raised px-2.5 py-1.5 shadow-lg text-xs whitespace-nowrap"
          style={{ left: `${(hoverX / W) * 100}%`, transform: `translateX(${hoverX > W / 2 ? '-100%' : '0'}) translateX(${hoverX > W / 2 ? '-8px' : '8px'})` }}
        >
          <div className="text-subtle font-mono mb-0.5">{fmtDate(points[hover].t)}</div>
          <div className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full" style={{ background: m.color }} />
            <span className="text-subtle">{m.label}</span>
            <span className="ml-auto pl-3 font-mono font-semibold text-content">{m.value(m.accessor(points[hover]), position)}</span>
          </div>
        </div>
      )}
    </div>
  )
}
