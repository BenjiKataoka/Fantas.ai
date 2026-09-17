import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

// Merge conditional + conflicting Tailwind classes (shadcn's standard helper).
export function cn(...inputs) {
  return twMerge(clsx(inputs))
}
