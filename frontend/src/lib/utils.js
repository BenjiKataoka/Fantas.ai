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

// One relative-time label for the whole app. Accepts an ISO string or a Date.
// `now` is a parameter so a component with its own ticking clock re-renders as it passes.
export function relativeTime(value, now = Date.now()) {
  if (!value) return ''
  const mins = Math.floor((now - new Date(value).getTime()) / 60000)
  if (mins < 1)  return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24)  return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

// Pull espn_s2 and SWID out of whatever the user pasted: the bookmarklet's output, a raw
// Cookie header, or a DevTools copy. Neither cookie is HttpOnly (checked 2026-09-24),
// which is what makes the one-click bookmarklet possible at all.
// Returns null unless BOTH are present, so a partial paste never half-fills the form.
export function parseEspnCookies(text) {
  if (!text || !/espn_s2/i.test(text)) return null
  const grab = (name) => {
    const m = text.match(new RegExp(`${name}\\s*[=:]\\s*"?([^;"\\s]+)`, 'i'))
    return m ? m[1] : ''
  }
  const espn_s2 = grab('espn_s2')
  let swid = grab('SWID')
  // ESPN's SWID is a GUID in braces and people lose them in transit; the API re-adds them,
  // but keep whatever shape we found so the field shows what was actually pasted.
  if (swid && !swid.startsWith('{')) swid = `{${swid.replace(/[{}]/g, '')}}`
  return espn_s2 && swid ? { espn_s2, swid } : null
}
