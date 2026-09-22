import { useEffect, useRef } from 'react'
import { useApp } from '../context/AppContext'

function lastName(name = '') {
  const parts = name.trim().split(/\s+/)
  return (parts[parts.length - 1] || name).toUpperCase()
}

// Market-style direction from the weighted projection tier.
function tier(v) {
  if (v == null) return { arrow: '·', color: 'text-subtle' }
  if (v >= 15)   return { arrow: '▲', color: 'text-bull' }
  if (v < 8)     return { arrow: '▼', color: 'text-bear' }
  return { arrow: '·', color: 'text-warn' }
}

const SPEED = 0.3 // px per frame (~18px/s), a calm drift

export default function Ticker() {
  const { rosterData } = useApp()
  const players = (rosterData?.roster || []).filter(p => p.weighted_proj != null)

  const scrollRef = useRef(null)
  const drag = useRef({ active: false, startX: 0, startScroll: 0 })
  const pos = useRef(0)                      // float accumulator (scrollLeft rounds to int on set)

  // One loop for the component's whole life: it reads the element each frame, so swapping
  // leagues (which empties the roster for a moment) can't leave the drift stopped.
  useEffect(() => {
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    let raf
    const step = () => {
      raf = requestAnimationFrame(step)
      const el = scrollRef.current
      if (!el) return
      if (!reduced && !drag.current.active) pos.current += SPEED
      const half = el.scrollWidth / 2
      if (half > 0) {
        if (pos.current >= half) pos.current -= half
        else if (pos.current < 0) pos.current += half
      }
      el.scrollLeft = pos.current
    }
    raf = requestAnimationFrame(step)

    // A release anywhere ends the drag. Without this, letting go off the strip (or while it
    // re-renders) left it "held" and the ticker never moved again.
    const release = () => { drag.current.active = false }
    window.addEventListener('pointerup', release)
    window.addEventListener('pointercancel', release)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('pointerup', release)
      window.removeEventListener('pointercancel', release)
    }
  }, [])

  // Keep the bar (and the loop's element) mounted while a league loads.
  if (!players.length) return <div className="border-b border-line bg-surface/70 h-8" />
  const strip = [...players, ...players] // duplicated for a seamless loop

  const onPointerDown = (e) => {
    drag.current = { active: true, startX: e.clientX, startScroll: pos.current }
    scrollRef.current?.setPointerCapture?.(e.pointerId)
  }
  const onPointerMove = (e) => {
    if (!drag.current.active || !scrollRef.current) return
    pos.current = drag.current.startScroll - (e.clientX - drag.current.startX)
    scrollRef.current.scrollLeft = pos.current
  }
  const endDrag = (e) => {
    if (!drag.current.active) return
    drag.current.active = false
    try { scrollRef.current?.releasePointerCapture?.(e.pointerId) } catch { /* already released */ }
  }

  return (
    <div className="border-b border-line bg-surface/70 ticker-mask">
      <div
        ref={scrollRef}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        className="overflow-x-hidden no-scrollbar cursor-grab active:cursor-grabbing select-none"
        style={{ touchAction: 'pan-y' }}
      >
        <div className="flex w-max">
          {strip.map((p, i) => {
            const t = tier(p.weighted_proj)
            return (
              <span key={i} className="flex items-center gap-1.5 px-4 py-1.5 text-xs whitespace-nowrap border-r border-line/50">
                <span className="font-display font-semibold tracking-wide text-content/75">{lastName(p.name)}</span>
                <span className="font-mono text-content tabular-nums">{p.weighted_proj.toFixed(1)}</span>
                <span className={`font-mono ${t.color}`}>{t.arrow}</span>
              </span>
            )
          })}
        </div>
      </div>
    </div>
  )
}
