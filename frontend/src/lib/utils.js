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
