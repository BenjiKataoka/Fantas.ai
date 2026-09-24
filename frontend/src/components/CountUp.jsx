import { useEffect, useRef, useState } from 'react'

/**
 * A number that rolls to its new value instead of snapping.
 *
 * Only worth using where a number changes while you are looking at it: the scoreboard
 * during the 60s game-day refresh. Everywhere else it is noise, so this is opt-in.
 * Holds still under prefers-reduced-motion, like every other effect in the app.
 */
export default function CountUp({ value, decimals = 1, duration = 500 }) {
  const [shown, setShown] = useState(value)
  const from = useRef(value)

  useEffect(() => {
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    const start = from.current
    if (value == null || reduced || start == null || start === value) {
      from.current = value
      setShown(value)
      return
    }
    const t0 = performance.now()
    let raf = requestAnimationFrame(function step(t) {
      const k = Math.min(1, (t - t0) / duration)
      const eased = 1 - Math.pow(1 - k, 3)   // ease-out: fast first, settles on the value
      setShown(start + (value - start) * eased)
      if (k < 1) raf = requestAnimationFrame(step)
      else from.current = value
    })
    return () => cancelAnimationFrame(raf)
  }, [value, duration])

  if (value == null) return '-'
  return (shown ?? value).toFixed(decimals)
}
