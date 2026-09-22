import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

// Merge conditional + conflicting Tailwind classes (shadcn's standard helper).
export function cn(...inputs) {
  return twMerge(clsx(inputs))
}

// Section enter motion shared by Tracker and Recap. Pair with a per-section
// animationDelay so sections land one after another, top to bottom.
export const REVEAL = 'animate-in fade-in-0 slide-in-from-top-2 duration-300 ease-out fill-mode-both'

// Sleeper's lineup slot names → what we show. Anything unlisted displays as-is.
const SLOT_LABELS = { SUPER_FLEX: 'SFLEX', WRRB_FLEX: 'W/R', REC_FLEX: 'W/T' }
export const slotLabel = (slot) => SLOT_LABELS[slot] || slot

// Bento-card tilt: spread onto an element with the .tilt class. Writes CSS variables
// directly so the card tilts toward the cursor without re-rendering React.
export const tiltHandlers = {
  onMouseMove(e) {
    const r = e.currentTarget.getBoundingClientRect()
    const x = (e.clientX - r.left) / r.width - 0.5
    const y = (e.clientY - r.top) / r.height - 0.5
    e.currentTarget.style.setProperty('--rx', `${(-y * 3).toFixed(2)}deg`)
    e.currentTarget.style.setProperty('--ry', `${(x * 3).toFixed(2)}deg`)
  },
  onMouseLeave(e) {
    e.currentTarget.style.setProperty('--rx', '0deg')
    e.currentTarget.style.setProperty('--ry', '0deg')
  },
}

// Dot-field spotlight: spread onto an element with the .dot-field class.
export const dotFieldHandlers = {
  onMouseMove(e) {
    const r = e.currentTarget.getBoundingClientRect()
    e.currentTarget.style.setProperty('--mx', `${e.clientX - r.left}px`)
    e.currentTarget.style.setProperty('--my', `${e.clientY - r.top}px`)
  },
  onMouseLeave(e) {
    e.currentTarget.style.setProperty('--mx', '-999px')
    e.currentTarget.style.setProperty('--my', '-999px')
  },
}
